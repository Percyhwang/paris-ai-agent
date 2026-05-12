from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.directions_service import RouteMode, get_route_leg
from app.services.place_repository_service import (
    PARIS_CENTER,
    distance_meters,
    find_nearby_meal_place,
    midpoint,
    resolve_place,
)

TIME_SLOTS = ["09:30", "12:30", "15:00", "18:30", "20:30"]


async def optimize_trip_payload(
    db: AsyncIOMotorDatabase,
    payload: dict[str, Any],
    prompt: str,
    language: str,
) -> dict[str, Any]:
    optimized = deepcopy(payload)
    route_mode = infer_route_mode(prompt, optimized.get("trip", {}).get("style_tags") or [])
    for day in optimized.get("itinerary_days", []):
        await _optimize_day(db, day, route_mode, language)

    trip = optimized.setdefault("trip", {})
    route_note = _route_note(route_mode, language)
    current_summary = str(trip.get("route_summary") or "").strip()
    if route_note not in current_summary:
        trip["route_summary"] = f"{current_summary} {route_note}".strip()
    return optimized


def infer_route_mode(prompt: str, style_tags: list[Any]) -> RouteMode:
    haystack = " ".join([prompt, *[str(tag) for tag in style_tags]]).lower()
    walk_keywords = ["walk", "walking", "on foot", "도보", "걸어서", "걷", "산책"]
    transit_keywords = ["transit", "metro", "subway", "bus", "rer", "train", "대중교통", "지하철", "버스"]
    if any(keyword in haystack for keyword in walk_keywords):
        return "walk"
    if any(keyword in haystack for keyword in transit_keywords):
        return "transit"
    return "mixed"


async def _optimize_day(
    db: AsyncIOMotorDatabase,
    day: dict[str, Any],
    route_mode: RouteMode,
    language: str,
) -> None:
    original_items = [dict(item) for item in day.get("items") or []]
    resolved_non_meals = []
    for item in original_items:
        if _is_meal_item(item):
            continue
        resolved = await _resolve_item_place(db, item)
        if resolved:
            resolved_non_meals.append(resolved)

    if not resolved_non_meals:
        return

    ordered = _nearest_neighbor_order(resolved_non_meals)
    enriched_items = await _with_meal_stops(db, ordered, language)
    _retime_items(enriched_items)
    await _attach_route_legs(enriched_items, route_mode, language)

    day["items"] = enriched_items
    day["route_summary"] = _day_route_summary(enriched_items, route_mode, language)


async def _resolve_item_place(db: AsyncIOMotorDatabase, item: dict[str, Any]) -> dict[str, Any] | None:
    place = dict(item.get("place") or {})
    name = str(place.get("name") or item.get("title") or "").strip()
    if not name:
        return None

    resolved_place = await resolve_place(
        db,
        name,
        category=place.get("category"),
        fallback_coordinates=place.get("coordinates"),
    )
    coordinates = resolved_place.get("coordinates") or place.get("coordinates")
    if not coordinates:
        return None

    resolved_item = dict(item)
    resolved_item["place"] = {**place, **resolved_place, "coordinates": coordinates}
    resolved_item["title"] = resolved_place.get("name") or resolved_item.get("title") or name
    return resolved_item


def _nearest_neighbor_order(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    remaining = [dict(item) for item in items]
    current = min(remaining, key=lambda item: distance_meters(PARIS_CENTER, _coordinates(item)))
    ordered = [current]
    remaining.remove(current)
    while remaining:
        previous_coordinates = _coordinates(ordered[-1])
        current = min(remaining, key=lambda item: distance_meters(previous_coordinates, _coordinates(item)))
        ordered.append(current)
        remaining.remove(current)
    return ordered


async def _with_meal_stops(
    db: AsyncIOMotorDatabase,
    ordered_items: list[dict[str, Any]],
    language: str,
) -> list[dict[str, Any]]:
    if not ordered_items:
        return []

    used_names = {str(item.get("place", {}).get("name") or item.get("title") or "").lower() for item in ordered_items}
    result: list[dict[str, Any]] = [ordered_items[0]]

    lunch_anchor = _meal_anchor(ordered_items, 0)
    lunch = await _meal_item(db, lunch_anchor, "lunch", language, used_names)
    if lunch:
        used_names.add(str(lunch.get("place", {}).get("name") or "").lower())
        result.append(lunch)

    middle_items = ordered_items[1:-1] if len(ordered_items) > 2 else ordered_items[1:]
    result.extend(middle_items)

    if len(ordered_items) >= 2:
        dinner_anchor = _meal_anchor(ordered_items, max(0, len(ordered_items) - 2))
        dinner = await _meal_item(db, dinner_anchor, "dinner", language, used_names)
        if dinner:
            used_names.add(str(dinner.get("place", {}).get("name") or "").lower())
            result.append(dinner)

    if len(ordered_items) > 2:
        result.append(ordered_items[-1])
    return result


async def _meal_item(
    db: AsyncIOMotorDatabase,
    anchor: dict[str, float],
    meal_type: str,
    language: str,
    used_names: set[str],
) -> dict[str, Any] | None:
    place = await find_nearby_meal_place(db, anchor, exclude_names=used_names)
    if not place or not place.get("coordinates"):
        return None

    title = _copy(
        language,
        f"{place['name']} {'lunch' if meal_type == 'lunch' else 'dinner'}",
        f"{place['name']} {'점심' if meal_type == 'lunch' else '저녁'}",
    )
    description = _copy(
        language,
        "Meal stop selected near the optimized route.",
        "최적화된 동선 근처에서 고른 식사 장소입니다.",
    )
    return {
        "id": str(uuid4()),
        "time_slot": "lunch" if meal_type == "lunch" else "evening",
        "start_time": "12:30" if meal_type == "lunch" else "18:30",
        "title": title,
        "place": place,
        "description": description,
        "estimated_duration": _copy(language, "1 hour", "1시간"),
    }


async def _attach_route_legs(
    items: list[dict[str, Any]],
    route_mode: RouteMode,
    language: str,
) -> None:
    for index, item in enumerate(items):
        item.pop("route_to_next", None)
        if index >= len(items) - 1:
            continue
        origin = _coordinates(item)
        destination = _coordinates(items[index + 1])
        item["route_to_next"] = await get_route_leg(origin, destination, route_mode, language)


def _retime_items(items: list[dict[str, Any]]) -> None:
    for index, item in enumerate(items):
        item["start_time"] = TIME_SLOTS[min(index, len(TIME_SLOTS) - 1)]


def _meal_anchor(items: list[dict[str, Any]], start_index: int) -> dict[str, float]:
    origin = _coordinates(items[start_index])
    if start_index + 1 < len(items):
        return midpoint(origin, _coordinates(items[start_index + 1]))
    return origin


def _coordinates(item: dict[str, Any]) -> dict[str, float]:
    coordinates = item.get("place", {}).get("coordinates") or PARIS_CENTER
    return {"lat": float(coordinates["lat"]), "lng": float(coordinates["lng"])}


def _is_meal_item(item: dict[str, Any]) -> bool:
    title = f"{item.get('title') or ''} {item.get('description') or ''}".lower()
    slot = item.get("time_slot")
    return slot == "lunch" or any(keyword in title for keyword in ["lunch", "dinner", "restaurant", "점심", "저녁", "식사"])


def _day_route_summary(items: list[dict[str, Any]], route_mode: RouteMode, language: str) -> str:
    leg_count = sum(1 for item in items if item.get("route_to_next"))
    mode_label = {
        "walk": _copy(language, "walking", "도보"),
        "transit": _copy(language, "transit", "대중교통"),
        "mixed": _copy(language, "short walks and transit", "짧은 도보와 대중교통"),
    }[route_mode]
    return _copy(
        language,
        f"Optimized with MongoDB place coordinates and {leg_count} {mode_label} legs.",
        f"MongoDB 장소 좌표 기준으로 {leg_count}개 {mode_label} 이동 구간을 최적화했습니다.",
    )


def _route_note(route_mode: RouteMode, language: str) -> str:
    labels = {
        "walk": _copy(language, "walking time", "도보 시간"),
        "transit": _copy(language, "metro/bus guidance", "지하철/버스 안내"),
        "mixed": _copy(language, "walking and transit guidance", "도보 및 대중교통 안내"),
    }
    return _copy(
        language,
        f"Movement details include {labels[route_mode]} between stops.",
        f"장소 사이 이동 정보에 {labels[route_mode]}를 포함했습니다.",
    )


def _copy(language: str, en: str, ko: str) -> str:
    return en if language == "en" else ko
