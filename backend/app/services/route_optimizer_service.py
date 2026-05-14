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

DAY_START_MINUTES = 9 * 60 + 15
LUNCH_START_MINUTES = 12 * 60
DINNER_START_MINUTES = 18 * 60 + 15
EVENING_START_MINUTES = 18 * 60

PACE_DURATION_MULTIPLIER = {
    "slow": 1.18,
    "normal": 1.0,
    "fast": 0.82,
}

STAY_DURATION_MINUTES = {
    "museum": 150,
    "gallery": 120,
    "landmark": 70,
    "cathedral": 55,
    "park": 80,
    "garden": 75,
    "neighborhood": 75,
    "cafe": 55,
    "restaurant": 90,
    "shopping": 95,
    "night_view": 55,
}

ROLE_ENERGY = {
    "museum": 4,
    "gallery": 3,
    "landmark": 2,
    "cathedral": 2,
    "park": 1,
    "garden": 1,
    "neighborhood": 2,
    "cafe": 1,
    "restaurant": 2,
    "shopping": 3,
    "night_view": 1,
}


async def optimize_trip_payload(
    db: AsyncIOMotorDatabase,
    payload: dict[str, Any],
    prompt: str,
    language: str,
) -> dict[str, Any]:
    optimized = deepcopy(payload)
    route_mode = infer_route_mode(prompt, optimized.get("trip", {}).get("style_tags") or [])
    pace_level = infer_pace_level(prompt, optimized.get("trip", {}).get("style_tags") or [])
    for day in optimized.get("itinerary_days", []):
        await _optimize_day(db, day, route_mode, pace_level, language)

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
    walk_keywords.extend(["\ub3c4\ubcf4", "\uac77\uae30", "\uac78\uc5b4"])
    transit_keywords.extend(["\ub300\uc911\uad50\ud1b5", "\uc9c0\ud558\ucca0", "\ubc84\uc2a4"])
    if any(keyword in haystack for keyword in walk_keywords):
        return "walk"
    if any(keyword in haystack for keyword in transit_keywords):
        return "transit"
    return "mixed"


def infer_pace_level(prompt: str, style_tags: list[Any]) -> str:
    haystack = " ".join([prompt, *[str(tag) for tag in style_tags]]).lower()
    slow_keywords = ["slow", "relaxed", "relax", "healing", "\uc5ec\uc720", "\ud734\uc2dd", "\ucc9c\ucc9c\ud788", "\ub290\uae0b"]
    fast_keywords = ["fast", "packed", "dense", "busy", "\ube61\ube61", "\uc54c\ucc28", "\ub9ce\uc774", "\ud0c0\uc774\ud2b8"]
    if any(keyword in haystack for keyword in slow_keywords):
        return "slow"
    if any(keyword in haystack for keyword in fast_keywords):
        return "fast"
    return "normal"


async def attach_route_legs_to_days(
    days: list[dict[str, Any]],
    *,
    prompt: str,
    style_tags: list[Any],
    language: str,
) -> RouteMode:
    route_mode = infer_route_mode(prompt, style_tags)
    pace_level = infer_pace_level(prompt, style_tags)
    for day in days:
        items = [dict(item) for item in day.get("items") or []]
        if not items:
            continue
        await _attach_route_legs(items, route_mode, language)
        _schedule_day(items, pace_level, language)
        day["items"] = items
        _apply_day_theme(day, language)
        day["route_summary"] = _day_route_summary(items, route_mode, language)
    return route_mode


async def _optimize_day(
    db: AsyncIOMotorDatabase,
    day: dict[str, Any],
    route_mode: RouteMode,
    pace_level: str,
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

    resolved_non_meals = _dedupe_items_by_place(resolved_non_meals)
    if not resolved_non_meals:
        return

    ordered = _experience_order(_nearest_neighbor_order(resolved_non_meals))
    enriched_items = await _with_meal_stops(db, ordered, language)
    await _attach_route_legs(enriched_items, route_mode, language)
    _schedule_day(enriched_items, pace_level, language)

    day["items"] = enriched_items
    _apply_day_theme(day, language)
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


def _experience_order(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(items) <= 2:
        return items

    early: list[dict[str, Any]] = []
    late: list[dict[str, Any]] = []
    for item in items:
        role = _role_key(item)
        if role == "night_view":
            late.append(item)
        else:
            early.append(item)

    if not early:
        return items

    anchor_index = next(
        (
            index
            for index, item in enumerate(early)
            if _role_key(item) in {"museum", "gallery", "landmark", "cathedral"}
        ),
        0,
    )
    anchor = early.pop(anchor_index)
    return [anchor, *early, *late]


def _dedupe_items_by_place(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique_items: list[dict[str, Any]] = []
    for item in items:
        keys = _item_place_keys(item)
        if any(key in seen for key in keys):
            continue
        seen.update(keys)
        unique_items.append(item)
    return unique_items


def _item_place_keys(item: dict[str, Any]) -> set[str]:
    place = item.get("place") or {}
    keys: set[str] = set()
    place_id = str(place.get("place_id") or "").strip().lower()
    if place_id:
        keys.add(f"id:{place_id}")
    name = str(place.get("name") or item.get("title") or "").strip().lower()
    if name:
        keys.add(f"name:{name}")
    coordinates = place.get("coordinates") or {}
    try:
        coordinate_key = f"{float(coordinates.get('lat')):.4f},{float(coordinates.get('lng')):.4f}"
    except (TypeError, ValueError):
        coordinate_key = ""
    if coordinate_key:
        keys.add(f"coord:{coordinate_key}")
    return keys


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
        _annotate_route_leg(item["route_to_next"], language)


def _schedule_day(items: list[dict[str, Any]], pace_level: str, language: str) -> None:
    current_minutes = DAY_START_MINUTES
    for index, item in enumerate(items):
        role = _role_key(item)
        if role == "restaurant" and _is_lunch_item(item):
            current_minutes = max(current_minutes, LUNCH_START_MINUTES)
        elif role == "restaurant":
            current_minutes = max(current_minutes, DINNER_START_MINUTES)
        elif role == "night_view":
            current_minutes = max(current_minutes, EVENING_START_MINUTES)

        duration = _stay_duration_minutes(item, role, pace_level)
        start_minutes = current_minutes
        end_minutes = start_minutes + duration
        item["start_time"] = _format_clock(start_minutes)
        item["end_time"] = _format_clock(end_minutes)
        item["duration_minutes"] = duration
        item["estimated_duration"] = _format_duration_minutes(duration, language)
        item["role_label"] = _role_label(role, item, language)
        item["role_icon"] = _role_icon(role)
        item["energy_level"] = ROLE_ENERGY.get(role, 2)
        item["reasoning"] = _experience_reasoning(item, role, index, len(items), language)

        route_to_next = item.get("route_to_next")
        if isinstance(route_to_next, dict):
            scheduled_seconds = int(route_to_next.get("scheduled_duration_seconds") or route_to_next.get("duration_seconds") or 0)
            current_minutes = end_minutes + max(1, round(scheduled_seconds / 60))
        else:
            current_minutes = end_minutes


def _annotate_route_leg(leg: dict[str, Any], language: str) -> None:
    duration_seconds = int(leg.get("duration_seconds") or 0)
    buffer_minutes = _route_buffer_minutes(leg)
    scheduled_seconds = duration_seconds + buffer_minutes * 60
    distance = int(leg.get("distance_meters") or 0)
    mode = str(leg.get("mode") or "walk")
    mode_label = {
        "walk": _copy(language, "Walk", "도보"),
        "transit": _copy(language, "Transit", "대중교통"),
    }.get(mode, _copy(language, "Move", "이동"))

    leg["buffer_minutes"] = buffer_minutes
    leg["scheduled_duration_seconds"] = scheduled_seconds
    leg["scheduled_duration_text"] = _format_duration_minutes(max(1, round(scheduled_seconds / 60)), language)
    leg["compact_summary"] = (
        f"{mode_label} {leg.get('duration_text') or _format_duration_minutes(max(1, round(duration_seconds / 60)), language)}"
        f" ({_format_distance(distance)})"
        if distance
        else f"{mode_label} {leg.get('duration_text') or _format_duration_minutes(max(1, round(duration_seconds / 60)), language)}"
    )


def _route_buffer_minutes(leg: dict[str, Any]) -> int:
    mode = str(leg.get("mode") or "walk")
    distance = int(leg.get("distance_meters") or 0)
    if mode == "transit":
        stop_count = sum(int(step.get("stop_count") or 0) for step in leg.get("steps") or [] if isinstance(step, dict))
        return 20 if stop_count >= 5 or leg.get("transit_lines") else 16
    if distance >= 1800:
        return 12
    return 9


def _role_key(item: dict[str, Any]) -> str:
    place = item.get("place") or {}
    title = str(item.get("title") or place.get("name") or "").lower()
    category = str(place.get("category") or "").lower()
    tags = " ".join(str(tag).lower() for tag in place.get("tags") or [])
    cuisine = place.get("cuisine")
    cuisine_text = " ".join(cuisine).lower() if isinstance(cuisine, list) else str(cuisine or "").lower()
    haystack = " ".join([title, category, tags, cuisine_text])

    if _is_meal_item(item):
        return "restaurant"
    if any(token in haystack for token in ("cafe", "coffee", "bakery", "카페")):
        return "cafe"
    if any(token in haystack for token in ("restaurant", "food", "meal", "dining", "bistro", "brasserie", "맛집", "식당")):
        return "restaurant"
    if any(token in haystack for token in ("museum", "gallery", "art_museum", "미술관", "박물관")):
        return "museum"
    if any(token in haystack for token in ("park", "garden", "botanical", "공원", "정원")):
        return "park"
    if any(token in haystack for token in ("shopping", "market", "store", "mall", "쇼핑")):
        return "shopping"
    if any(token in haystack for token in ("sunset", "night", "view", "seine", "eiffel", "야경", "전망")):
        return "night_view"
    if any(token in haystack for token in ("cathedral", "church", "chapel", "성당")):
        return "cathedral"
    if any(token in haystack for token in ("neighborhood", "quarter", "street", "marais", "montmartre", "동네", "거리")):
        return "neighborhood"
    return "landmark"


def _is_lunch_item(item: dict[str, Any]) -> bool:
    text = f"{item.get('time_slot') or ''} {item.get('title') or ''} {item.get('description') or ''}".lower()
    return "lunch" in text or "점심" in text


def _stay_duration_minutes(item: dict[str, Any], role: str, pace_level: str) -> int:
    if _is_lunch_item(item):
        base = 75
    elif role == "restaurant":
        base = STAY_DURATION_MINUTES["restaurant"]
    else:
        base = STAY_DURATION_MINUTES.get(role, 65)
    multiplier = PACE_DURATION_MULTIPLIER.get(pace_level, 1.0)
    adjusted = round(base * multiplier / 5) * 5
    if role in {"cafe", "park", "night_view"}:
        return max(35, min(adjusted, 110))
    if role == "museum":
        return max(90, min(adjusted, 210))
    return max(40, min(adjusted, 150))


def _role_label(role: str, item: dict[str, Any], language: str) -> str:
    if role == "restaurant":
        return _copy(language, "Lunch stop" if _is_lunch_item(item) else "Dinner restaurant", "점심 식사" if _is_lunch_item(item) else "저녁 레스토랑")
    labels = {
        "museum": _copy(language, "Art & museum focus", "예술 감상"),
        "gallery": _copy(language, "Gallery stop", "예술 감상"),
        "landmark": _copy(language, "Core landmark", "핵심 명소"),
        "cathedral": _copy(language, "Historic landmark", "역사 명소"),
        "park": _copy(language, "Gentle reset", "쉬어가는 산책"),
        "garden": _copy(language, "Garden reset", "쉬어가는 산책"),
        "neighborhood": _copy(language, "Neighborhood walk", "동네 산책"),
        "cafe": _copy(language, "Cafe pause", "쉬어가는 카페"),
        "shopping": _copy(language, "Shopping rhythm", "쇼핑 타임"),
        "night_view": _copy(language, "Evening view", "야경 스팟"),
    }
    return labels.get(role, _copy(language, "Paris stop", "파리 스팟"))


def _role_icon(role: str) -> str:
    return {
        "museum": "🖼",
        "gallery": "🖼",
        "landmark": "🎭",
        "cathedral": "⛪",
        "park": "🌿",
        "garden": "🌿",
        "neighborhood": "🚶",
        "cafe": "☕",
        "restaurant": "🍷",
        "shopping": "🛍",
        "night_view": "🌇",
    }.get(role, "📍")


def _experience_reasoning(item: dict[str, Any], role: str, index: int, total_items: int, language: str) -> str:
    place = item.get("place") or {}
    title = str(place.get("name") or item.get("title") or "")
    if language == "en":
        if index == 0:
            return f"Start here while attention and energy are fresh, then let the rest of the day build around {title}."
        if role == "restaurant":
            return "This meal break lands near the natural pause in the route, keeping the day from becoming a forced march."
        if role == "cafe":
            return "This is intentionally paced as a reset stop, giving you time to sit down before the next highlight."
        if role == "night_view" or index == total_items - 1:
            return "Placed late in the day so the light and atmosphere feel like a closing moment rather than another checklist stop."
        if role in {"museum", "gallery"}:
            return "The visit gets a longer block so you can focus on the collection instead of rushing between rooms."
        return "Placed here to keep the neighborhood flow coherent while leaving enough buffer for real-world movement."

    if index == 0:
        return f"하루 초반 집중력이 좋을 때 {title}을 먼저 배치해 감상 밀도를 높였습니다."
    if role == "restaurant":
        return "동선이 끊기지 않는 지점에 식사 시간을 넣어 오후 일정 전에 자연스럽게 숨을 고를 수 있습니다."
    if role == "cafe":
        return "다음 핵심 장소로 넘어가기 전 앉아서 쉬는 리듬을 만들기 위한 완충 스팟입니다."
    if role == "night_view" or index == total_items - 1:
        return "하루의 마지막 인상이 남도록 빛과 분위기가 좋아지는 시간대에 배치했습니다."
    if role in {"museum", "gallery"}:
        return "작품을 훑고 지나가지 않도록 체류 시간을 길게 잡아 감상 여유를 확보했습니다."
    return "동네 흐름을 유지하면서도 실제 이동과 사진 촬영 시간을 감안해 배치했습니다."


def _meal_anchor(items: list[dict[str, Any]], start_index: int) -> dict[str, float]:
    origin = _coordinates(items[start_index])
    if start_index + 1 < len(items):
        return midpoint(origin, _coordinates(items[start_index + 1]))
    return origin


def _apply_day_theme(day: dict[str, Any], language: str) -> None:
    items = [dict(item) for item in day.get("items") or []]
    if not items:
        return
    title = _day_theme_title(int(day.get("day_number") or 1), items, language)
    day["theme"] = title
    day["title"] = title


def _day_theme_title(day_number: int, items: list[dict[str, Any]], language: str) -> str:
    roles = [_role_key(item) for item in items]
    if "museum" in roles or "gallery" in roles:
        theme = _copy(language, "Art, Icons & Slow Looking", "예술과 명소를 천천히 감상하는 날")
    elif "night_view" in roles:
        theme = _copy(language, "Classic Paris with an Evening View", "클래식 파리와 야경으로 마무리")
    elif "cafe" in roles and "neighborhood" in roles:
        theme = _copy(language, "Cafe Streets & Local Walks", "카페 거리와 로컬 산책")
    elif "shopping" in roles:
        theme = _copy(language, "Shopping, Cafes & Easy Wandering", "쇼핑과 카페를 곁들인 여유 코스")
    elif "park" in roles:
        theme = _copy(language, "Green Breaks Between Paris Highlights", "초록 쉼표가 있는 파리 명소 코스")
    else:
        theme = _copy(language, "Paris Highlights with a Human Pace", "사람답게 걷는 파리 핵심 코스")
    return _copy(language, f"Day {day_number} - {theme}", f"Day {day_number} - {theme}")


def _format_clock(minutes: int) -> str:
    minutes = max(0, minutes)
    hours, minute_remainder = divmod(minutes, 60)
    return f"{hours:02d}:{minute_remainder:02d}"


def _format_duration_minutes(minutes: int, language: str) -> str:
    minutes = max(1, int(minutes))
    hours, minute_remainder = divmod(minutes, 60)
    if language == "en":
        if hours and minute_remainder:
            return f"{hours} hr {minute_remainder} min"
        if hours:
            return f"{hours} hr"
        return f"{minutes} min"
    if hours and minute_remainder:
        return f"{hours}시간 {minute_remainder}분"
    if hours:
        return f"{hours}시간"
    return f"{minutes}분"


def _format_distance(meters: int) -> str:
    if meters >= 1000:
        return f"{meters / 1000:.1f} km"
    return f"{meters} m"


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
