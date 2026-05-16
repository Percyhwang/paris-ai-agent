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
GAP_DISCLOSURE_MINUTES = 15
MEAL_PLACE_CATEGORIES = {"bar", "bakery", "bistro", "brasserie", "cafe", "restaurant", "wine_bar"}

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


def _preference_profile(prompt: str, style_tags: list[Any], planning_brief: dict[str, Any] | None = None) -> dict[str, Any]:
    brief = planning_brief or {}
    tokens = [str(tag).lower() for tag in style_tags]
    brief_style = [str(tag).lower() for tag in brief.get("travel_style") or []]
    meal_preferences = [str(tag).lower() for tag in brief.get("meal_preference") or []]
    haystack = " ".join([prompt.lower(), *tokens, *brief_style, *meal_preferences])
    pace_level = _pace_level_from_brief(brief) or infer_pace_level(prompt, style_tags)
    route_mode = _route_mode_from_brief(brief) or infer_route_mode(prompt, style_tags)
    return {
        "night_view": bool(brief.get("night_view_required")) or any(token in haystack for token in ("night_view", "night", "view", "야경", "석양", "선셋")),
        "museum": any(token in haystack for token in ("museum", "art", "미술관", "박물관", "예술")),
        "local": any(token in haystack for token in ("local", "hidden_gems", "walk", "로컬", "골목", "산책")),
        "shopping": any(token in haystack for token in ("shopping", "쇼핑")),
        "foodie": any(token in haystack for token in ("foodie", "cafe", "맛집", "카페", "브런치")),
        "slow": pace_level == "slow",
        "fast": pace_level == "fast",
        "route_mode": route_mode,
        "style_tags": list(dict.fromkeys([*tokens, *brief_style])),
        "planning_brief": brief,
    }


async def optimize_trip_payload(
    db: AsyncIOMotorDatabase,
    payload: dict[str, Any],
    prompt: str,
    language: str,
    planning_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    optimized = deepcopy(payload)
    brief = planning_brief or optimized.get("planning_brief") or optimized.get("trip", {}).get("planning_brief") or {}
    route_mode = _route_mode_from_brief(brief) or infer_route_mode(prompt, optimized.get("trip", {}).get("style_tags") or [])
    pace_level = _pace_level_from_brief(brief) or infer_pace_level(prompt, optimized.get("trip", {}).get("style_tags") or [])
    preference_profile = _preference_profile(prompt, optimized.get("trip", {}).get("style_tags") or [], brief)
    itinerary_days = list(optimized.get("itinerary_days") or [])
    total_days = len(itinerary_days)
    for day_index, day in enumerate(itinerary_days):
        await _optimize_day(db, day, route_mode, pace_level, language, preference_profile, day_index, total_days)

    trip = optimized.setdefault("trip", {})
    trip["planning_brief"] = brief
    optimized["planning_brief"] = brief
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
    planning_brief: dict[str, Any] | None = None,
) -> RouteMode:
    brief = planning_brief or {}
    route_mode = _route_mode_from_brief(brief) or infer_route_mode(prompt, style_tags)
    pace_level = _pace_level_from_brief(brief) or infer_pace_level(prompt, style_tags)
    preference_profile = _preference_profile(prompt, style_tags, brief)
    total_days = len(days)
    for day_index, day in enumerate(days):
        items = [dict(item) for item in day.get("items") or []]
        if not items:
            continue
        await _attach_route_legs(items, route_mode, language)
        day["items"] = _schedule_day(items, pace_level, language, preference_profile)
        _apply_day_theme(day, language, preference_profile, day_index, total_days)
        _enrich_day_story(day, day["items"], route_mode, preference_profile, language)
    return route_mode


def _route_mode_from_brief(planning_brief: dict[str, Any]) -> RouteMode | None:
    preference = str(planning_brief.get("transport_preference") or "").lower()
    if preference == "walk":
        return "walk"
    if preference == "transit":
        return "transit"
    if preference in {"both", "mixed"}:
        return "mixed"
    return None


def _pace_level_from_brief(planning_brief: dict[str, Any]) -> str | None:
    value = str(planning_brief.get("pace") or "").lower()
    return value if value in {"slow", "normal", "fast"} else None


async def _optimize_day(
    db: AsyncIOMotorDatabase,
    day: dict[str, Any],
    route_mode: RouteMode,
    pace_level: str,
    language: str,
    preference_profile: dict[str, Any],
    day_index: int,
    total_days: int,
) -> None:
    original_items = [dict(item) for item in day.get("items") or []]
    preserve_planner_story = bool(day.get("blueprintArchetype") or day.get("dayArchetype")) and _has_explicit_story_order(original_items)
    if preserve_planner_story:
        resolved_items: list[dict[str, Any]] = []
        for item in original_items:
            resolved = await _resolve_item_place(db, item) or dict(item)
            resolved_items.append(resolved)
        resolved_items = _dedupe_items_by_place(resolved_items)
        if not resolved_items:
            return
        await _attach_route_legs(resolved_items, route_mode, language)
        day["items"] = _schedule_day(resolved_items, pace_level, language, preference_profile)
        _apply_day_theme(day, language, preference_profile, day_index, total_days)
        _enrich_day_story(day, day["items"], route_mode, preference_profile, language)
        return

    resolved_non_meals = []
    planned_lunch: dict[str, Any] | None = None
    planned_dinner: dict[str, Any] | None = None
    for item in original_items:
        if _is_lunch_item(item):
            planned_lunch = await _resolve_item_place(db, item) or dict(item)
            continue
        if _is_meal_item(item):
            planned_dinner = await _resolve_item_place(db, item) or dict(item)
            continue
        resolved = await _resolve_item_place(db, item) or dict(item)
        resolved_non_meals.append(resolved)

    resolved_non_meals = _dedupe_items_by_place(resolved_non_meals)
    if not resolved_non_meals:
        return

    ordered = _story_order(resolved_non_meals)
    enriched_items = await _with_meal_stops(
        db,
        ordered,
        language,
        planned_lunch=planned_lunch,
        planned_dinner=planned_dinner,
        preference_profile=preference_profile,
    )
    await _attach_route_legs(enriched_items, route_mode, language)
    day["items"] = _schedule_day(enriched_items, pace_level, language, preference_profile)
    _apply_day_theme(day, language, preference_profile, day_index, total_days)
    _enrich_day_story(day, day["items"], route_mode, preference_profile, language)


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


def _story_order(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        return []
    if _has_explicit_story_order(items):
        return sorted(
            items,
            key=lambda item: (
                _parse_clock_minutes(item.get("start_time")) is None,
                _parse_clock_minutes(item.get("start_time")) or 0,
            ),
        )
    return _experience_order(_nearest_neighbor_order(items))


def _has_explicit_story_order(items: list[dict[str, Any]]) -> bool:
    explicit_count = sum(1 for item in items if _parse_clock_minutes(item.get("start_time")) is not None)
    return explicit_count >= max(2, len(items) - 1)


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
    planned_lunch: dict[str, Any] | None = None,
    planned_dinner: dict[str, Any] | None = None,
    preference_profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not ordered_items:
        return []
    preference_profile = preference_profile or {}

    used_names = {str(item.get("place", {}).get("name") or item.get("title") or "").lower() for item in ordered_items}
    result: list[dict[str, Any]] = [ordered_items[0]]

    lunch_anchor = _meal_anchor(ordered_items, 0)
    lunch = planned_lunch if _is_valid_meal_candidate(planned_lunch, lunch_anchor, used_names) else None
    lunch = lunch or await _meal_item(db, lunch_anchor, "lunch", language, used_names)
    if lunch:
        lunch = dict(lunch)
        place_name = str((lunch.get("place") or {}).get("name") or lunch.get("title") or "").strip()
        if place_name and not _is_lunch_item(lunch):
            lunch["title"] = _copy(language, f"{place_name} lunch", f"{place_name} 점심")
        lunch["description"] = _meal_description(
            "lunch",
            language,
            preference_profile,
            next_stop=ordered_items[1] if len(ordered_items) > 1 else None,
        )
        used_names.add(str(lunch.get("place", {}).get("name") or "").lower())
        lunch["time_slot"] = "lunch"
        result.append(lunch)

    middle_items = ordered_items[1:-1]
    result.extend(middle_items)

    if len(ordered_items) >= 2:
        dinner_anchor = _meal_anchor(ordered_items, max(0, len(ordered_items) - 2))
        dinner = planned_dinner if _is_valid_meal_candidate(planned_dinner, dinner_anchor, used_names) else None
        dinner = dinner or await _meal_item(db, dinner_anchor, "dinner", language, used_names)
        if dinner:
            dinner = dict(dinner)
            place_name = str((dinner.get("place") or {}).get("name") or dinner.get("title") or "").strip()
            if place_name and not _is_dinner_item(dinner):
                dinner["title"] = _copy(language, f"{place_name} dinner", f"{place_name} 저녁")
            dinner["description"] = _meal_description(
                "dinner",
                language,
                preference_profile,
                next_stop=ordered_items[-1] if len(ordered_items) > 1 else None,
            )
            used_names.add(str(dinner.get("place", {}).get("name") or "").lower())
            dinner["time_slot"] = "evening"
            result.append(dinner)

    if len(ordered_items) >= 2:
        result.append(ordered_items[-1])
    return result


def _normalize_scheduled_time_slot(item: dict[str, Any], role: str, start_minutes: int) -> str:
    if role in {"restaurant", "meal_placeholder"}:
        return "lunch" if _is_lunch_item(item) and start_minutes < 15 * 60 else "evening"
    if start_minutes < 12 * 60:
        return "morning"
    if start_minutes < 17 * 60:
        return "afternoon"
    return "evening"


async def _meal_item(
    db: AsyncIOMotorDatabase,
    anchor: dict[str, float],
    meal_type: str,
    language: str,
    used_names: set[str],
) -> dict[str, Any] | None:
    place = await find_nearby_meal_place(db, anchor, exclude_names=used_names)
    if not place or not place.get("coordinates"):
        return _meal_placeholder_item(anchor, meal_type, language)

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


def _meal_placeholder_item(anchor: dict[str, float], meal_type: str, language: str) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "time_slot": "lunch" if meal_type == "lunch" else "evening",
        "start_time": "12:30" if meal_type == "lunch" else "18:30",
        "title": _copy(language, "Nearby meal choice needed", "근처 식사 후보 확인 필요"),
        "place": {
            "name": _copy(language, "Nearby meal choice needed", "근처 식사 후보 확인 필요"),
            "category": "meal_placeholder",
            "coordinates": anchor,
        },
        "description": _copy(
            language,
            "No reliable restaurant or cafe candidate was found close enough to the surrounding route yet.",
            "주변 동선 가까이에서 신뢰할 만한 식당·카페를 아직 확정하지 못해, 근처 식사 후보 확인이 필요한 상태입니다.",
        ),
        "estimated_duration": _copy(language, "1 hour", "1시간"),
        "nearbyMealNeeded": True,
    }


def _is_valid_meal_candidate(item: dict[str, Any] | None, anchor: dict[str, float], used_names: set[str]) -> bool:
    if not isinstance(item, dict):
        return False
    place = item.get("place") or {}
    place_name = str(place.get("name") or item.get("title") or "").strip().lower()
    if not place_name or place_name in used_names:
        return False
    category = str(place.get("category") or "").lower()
    text = " ".join(
        [
            str(item.get("title") or ""),
            str(item.get("description") or ""),
            str(place.get("name") or ""),
            category,
        ]
    ).lower()
    if category not in MEAL_PLACE_CATEGORIES and not any(
        token in text for token in ("restaurant", "cafe", "bakery", "bar", "bistro", "brasserie", "wine", "점심", "저녁", "식사")
    ):
        return False
    coordinates = place.get("coordinates")
    if not isinstance(coordinates, dict) or coordinates.get("lat") is None or coordinates.get("lng") is None:
        return False
    try:
        point = {"lat": float(coordinates["lat"]), "lng": float(coordinates["lng"])}
    except (TypeError, ValueError):
        return False
    return distance_meters(anchor, point) <= 2200


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


def _schedule_day(
    items: list[dict[str, Any]],
    pace_level: str,
    language: str,
    preference_profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    preference_profile = preference_profile or {}
    scheduled_items: list[dict[str, Any]] = []
    current_minutes = _initial_day_start_minutes(items, pace_level)
    for index, item in enumerate(items):
        item = dict(item)
        role = _role_key(item)
        next_item = items[index + 1] if index + 1 < len(items) else None
        next_role = _role_key(next_item) if isinstance(next_item, dict) else ""
        next_name = str((next_item or {}).get("place", {}).get("name") or (next_item or {}).get("title") or "").strip()
        preferred_start = _preferred_start_minutes(item, role)
        if preferred_start is not None and preferred_start > current_minutes:
            wait_minutes = preferred_start - current_minutes
            can_pull_forward = wait_minutes >= 60 and role not in {"night_view", "meal_placeholder"}
            if can_pull_forward:
                preferred_start = current_minutes
                wait_minutes = 0
            if wait_minutes >= GAP_DISCLOSURE_MINUTES:
                scheduled_items.append(_gap_item(item, current_minutes, preferred_start, preference_profile, language))
            current_minutes = preferred_start

        duration = _stay_duration_minutes(item, role, pace_level)
        start_minutes = current_minutes
        end_minutes = start_minutes + duration
        item["itemKind"] = "gap" if role == "gap" else "stop"
        item["gapReason"] = item.get("gapReason") if role == "gap" else None
        item["time_slot"] = _normalize_scheduled_time_slot(item, role, start_minutes)
        item["start_time"] = _format_clock(start_minutes)
        item["end_time"] = _format_clock(end_minutes)
        item["duration_minutes"] = duration
        item["estimated_duration"] = _format_duration_minutes(duration, language)
        item["role_label"] = _role_label(role, item, language)
        item["role_icon"] = _role_icon(role)
        item["energy_level"] = ROLE_ENERGY.get(role, 2)
        item["isNightViewSpot"] = bool(item.get("isNightViewSpot")) or role == "night_view" or bool(item.get("slotLockReason"))
        item["slotPurpose"] = str(item.get("slotPurpose") or _slot_purpose(item, role, index, len(items), preference_profile, language))
        item["userPreferenceReason"] = str(item.get("userPreferenceReason") or _user_preference_reason(item, role, preference_profile, language))
        item["timeReason"] = str(item.get("timeReason") or _time_reason(item, role, index, len(items), preference_profile, language))
        item["expectedExperience"] = str(item.get("expectedExperience") or _expected_experience(item, role, language))
        item["editableReason"] = str(item.get("editableReason") or _editable_reason(item, role, language))
        item["nearbyMealNeeded"] = bool(item.get("nearbyMealNeeded"))
        if role == "meal_placeholder":
            item["slotPurpose"] = _copy(
                language,
                "A real meal venue still needs to be confirmed close to this part of the route.",
                "이 구간에서는 실제 식사 장소를 근처에서 한 번 더 확정해야 합니다.",
            )
            item["userPreferenceReason"] = _copy(
                language,
                "The planner refused to fill a meal slot with a landmark, so it leaves a visible meal-choice checkpoint instead.",
                "랜드마크를 식사 슬롯에 끼워 넣지 않기 위해, 임시 대체 대신 식사 후보 확인이 필요한 상태를 그대로 드러냈습니다.",
            )
            item["timeReason"] = _copy(
                language,
                "The meal window is preserved here so you can choose a nearby restaurant without breaking the rest of the day.",
                "이 시간대를 비워 두지 않고 유지해, 근처 식당으로 바꿔도 하루 흐름이 크게 흔들리지 않도록 했습니다.",
            )
            item["expectedExperience"] = _copy(
                language,
                "Use this checkpoint to pick a restaurant or cafe that matches your budget and mood.",
                "예산과 분위기에 맞는 식당이나 카페를 이 구간에서 고르는 용도로 보면 됩니다.",
            )
            item["editableReason"] = _copy(
                language,
                "Replace this with any nearby restaurant, cafe, bakery, or wine bar and keep the timeline intact.",
                "근처 레스토랑, 카페, 베이커리, 와인바 중 한 곳으로 바꾸면 전체 시간표는 그대로 유지하기 쉽습니다.",
            )
        if role == "restaurant" and next_role == "night_view" and preference_profile.get("night_view"):
            item["userPreferenceReason"] = _copy(
                language,
                f"Placed as dinner before {next_name} so the night-view leg feels connected instead of rushed.",
                f"야경 취향을 반영해 {next_name}로 넘어가기 전에 저녁 식사로 숨을 고르도록 배치했습니다.",
            )
            item["timeReason"] = _copy(
                language,
                "Timed so you can eat first, then arrive at the evening-view stop once the light matters.",
                "식사 뒤 해가 진 시간대에 야경 포인트로 도착하도록 저녁 구간으로 고정했습니다.",
            )
        elif role == "restaurant" and _is_lunch_item(item) and preference_profile.get("slow"):
            item["userPreferenceReason"] = _copy(
                language,
                "Matched to a slower pace by treating lunch as a real pause rather than a quick stop.",
                "slow pace에 맞춰 점심을 빠른 중간 정차가 아니라 실제로 앉아 쉬는 블록처럼 배치했습니다.",
            )
        item["reasoning"] = item["userPreferenceReason"] or _experience_reasoning(item, role, index, len(items), language)
        scheduled_items.append(item)

        route_to_next = item.get("route_to_next")
        if isinstance(route_to_next, dict):
            transfer_minutes = _transfer_minutes_from_leg(route_to_next)
            item["restBufferReason"] = str(route_to_next.get("restBufferReason") or "")
            current_minutes = end_minutes + max(1, transfer_minutes)
        else:
            item["restBufferReason"] = None
            current_minutes = end_minutes
    items[:] = scheduled_items
    return items


def _annotate_route_leg(leg: dict[str, Any], language: str) -> None:
    duration_seconds = int(leg.get("duration_seconds") or 0)
    raw_minutes = max(1, round(duration_seconds / 60))
    buffer_minutes = _route_buffer_minutes(leg)
    total_transfer_minutes = raw_minutes + buffer_minutes
    scheduled_seconds = total_transfer_minutes * 60
    distance = int(leg.get("distance_meters") or 0)
    mode = str(leg.get("mode") or "walk")
    mode_label = {
        "walk": _copy(language, "Walk", "도보"),
        "transit": _copy(language, "Transit", "대중교통"),
    }.get(mode, _copy(language, "Move", "이동"))

    leg["buffer_minutes"] = buffer_minutes
    leg["rawDurationMinutes"] = raw_minutes
    leg["bufferMinutes"] = buffer_minutes
    leg["totalTransferMinutes"] = total_transfer_minutes
    leg["scheduled_duration_seconds"] = scheduled_seconds
    leg["scheduled_duration_text"] = _format_duration_minutes(total_transfer_minutes, language)
    effort_level = _effort_level(mode, scheduled_seconds, distance)
    burden_copy = {
        "low": _copy(language, "low effort", "이동 부담 낮음"),
        "medium": _copy(language, "moderate effort", "이동 부담 보통"),
        "high": _copy(language, "higher effort", "이동 부담 높음"),
    }[effort_level]
    move_copy = {
        "walk": _copy(language, "Walkable", "도보 가능"),
        "transit": _copy(language, "Transit needed", "대중교통 필요"),
    }.get(mode, _copy(language, "Mixed move", "도보+대중교통"))
    leg["effort_level"] = effort_level
    leg["comfort_summary"] = f"{move_copy} · {burden_copy}"
    leg["restBufferReason"] = _route_buffer_reason(mode, buffer_minutes, language)
    leg["compact_summary"] = (
        f"{leg['comfort_summary']} · {_format_duration_minutes(total_transfer_minutes, language)}"
        f" ({_format_distance(distance)})"
        if distance
        else f"{leg['comfort_summary']} · {_format_duration_minutes(total_transfer_minutes, language)}"
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


def _effort_level(mode: str, scheduled_seconds: int, distance: int) -> str:
    minutes = max(1, round(scheduled_seconds / 60))
    if mode == "transit":
        if minutes <= 25:
            return "low"
        if minutes <= 45:
            return "medium"
        return "high"
    if distance <= 1200 and minutes <= 18:
        return "low"
    if distance <= 2600 and minutes <= 35:
        return "medium"
    return "high"


def _route_buffer_reason(mode: str, buffer_minutes: int, language: str) -> str:
    if mode == "transit":
        return _copy(
            language,
            f"Includes about {buffer_minutes} minutes for platforms, exits, and small delays.",
            f"환승, 출구 이동, 작은 지연까지 감안해 약 {buffer_minutes}분 여유를 두었습니다.",
        )
    return _copy(
        language,
        f"Keeps about {buffer_minutes} minutes for photos, crossings, and a natural walking pace.",
        f"사진 촬영, 횡단보도, 자연스러운 보행 속도를 고려해 약 {buffer_minutes}분 여유를 두었습니다.",
    )


def _role_key(item: dict[str, Any]) -> str:
    if item.get("itemKind") == "gap" or str((item.get("place") or {}).get("category") or "").lower() == "free_time":
        return "gap"
    place = item.get("place") or {}
    title = str(item.get("title") or place.get("name") or "").lower()
    category = str(place.get("category") or "").lower()
    slot = str(item.get("time_slot") or "").lower()
    tags = " ".join(str(tag).lower() for tag in place.get("tags") or [])
    cuisine = place.get("cuisine")
    cuisine_text = " ".join(cuisine).lower() if isinstance(cuisine, list) else str(cuisine or "").lower()
    haystack = " ".join([title, category, tags, cuisine_text])

    if item.get("nearbyMealNeeded") or category == "meal_placeholder":
        return "meal_placeholder"
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
    if any(token in haystack for token in ("sunset", "night", "night_view", "야경", "전망")):
        return "night_view"
    if slot == "evening" and any(token in haystack for token in ("seine", "eiffel", "pont des arts", "river", "tower")):
        return "night_view"
    if any(token in haystack for token in ("cathedral", "church", "chapel", "성당")):
        return "cathedral"
    if any(token in haystack for token in ("neighborhood", "quarter", "street", "marais", "montmartre", "동네", "거리")):
        return "neighborhood"
    return "landmark"


def _is_lunch_item(item: dict[str, Any]) -> bool:
    text = f"{item.get('time_slot') or ''} {item.get('title') or ''} {item.get('description') or ''}".lower()
    return "lunch" in text or "점심" in text


def _is_dinner_item(item: dict[str, Any]) -> bool:
    text = f"{item.get('time_slot') or ''} {item.get('title') or ''} {item.get('description') or ''}".lower()
    return "dinner" in text or "저녁" in text


def _preferred_start_minutes(item: dict[str, Any], role: str) -> int | None:
    preferred = _parse_clock_minutes(item.get("start_time"))
    if role == "restaurant" and _is_lunch_item(item):
        return max(preferred or LUNCH_START_MINUTES, LUNCH_START_MINUTES)
    if role == "restaurant":
        return max(preferred or DINNER_START_MINUTES, DINNER_START_MINUTES)
    if role == "night_view":
        return max(preferred or EVENING_START_MINUTES, EVENING_START_MINUTES)
    return preferred


def _parse_clock_minutes(value: Any) -> int | None:
    raw = str(value or "").strip()
    if ":" not in raw:
        return None
    try:
        hour, minute = raw.split(":", 1)
        return int(hour) * 60 + int(minute)
    except ValueError:
        return None


def _initial_day_start_minutes(items: list[dict[str, Any]], pace_level: str) -> int:
    if not items:
        return DAY_START_MINUTES

    first_item = items[0]
    first_pref = _preferred_start_minutes(first_item, _role_key(first_item))
    lower_bound = max(DAY_START_MINUTES, first_pref or DAY_START_MINUTES)

    required_before = 0
    latest_viable_starts: list[int] = []
    for index, item in enumerate(items):
        role = _role_key(item)
        if index > 0:
            preferred_start = _preferred_start_minutes(item, role)
            if preferred_start is not None:
                latest_viable_starts.append(preferred_start - required_before)
        required_before += _stay_duration_minutes(item, role, pace_level)
        required_before += _transfer_minutes_from_leg(item.get("route_to_next"))

    if not latest_viable_starts:
        return lower_bound

    latest_feasible = min(latest_viable_starts)
    if latest_feasible >= lower_bound:
        return latest_feasible
    return lower_bound


def _transfer_minutes_from_leg(route_to_next: Any) -> int:
    if not isinstance(route_to_next, dict):
        return 0
    return int(
        route_to_next.get("totalTransferMinutes")
        or round(int(route_to_next.get("scheduled_duration_seconds") or 0) / 60)
        or route_to_next.get("rawDurationMinutes")
        or max(1, round(int(route_to_next.get("duration_seconds") or 0) / 60))
    )


def _stay_duration_minutes(item: dict[str, Any], role: str, pace_level: str) -> int:
    if _is_lunch_item(item):
        base = 75
    elif role in {"restaurant", "meal_placeholder"}:
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


def _gap_item(
    anchor_item: dict[str, Any],
    start_minutes: int,
    end_minutes: int,
    preference_profile: dict[str, Any],
    language: str,
) -> dict[str, Any]:
    duration = max(1, end_minutes - start_minutes)
    gap_reason = _gap_reason(anchor_item, duration, preference_profile, language)
    title = _gap_title(anchor_item, duration, preference_profile, language)
    return {
        "id": str(uuid4()),
        "itemKind": "gap",
        "gapReason": gap_reason,
        "time_slot": _time_slot_for_minutes(start_minutes),
        "start_time": _format_clock(start_minutes),
        "end_time": _format_clock(end_minutes),
        "title": title,
        "place": {
            "name": title,
            "category": "free_time",
            "coordinates": None,
        },
        "description": gap_reason,
        "estimated_duration": _format_duration_minutes(duration, language),
        "duration_minutes": duration,
        "role_label": _copy(language, "Recommended buffer", "추천 여유 시간"),
        "role_icon": "⏳",
        "reasoning": gap_reason,
        "slotPurpose": gap_reason,
        "userPreferenceReason": gap_reason,
        "timeReason": _copy(
            language,
            "This visible buffer keeps the next start time feasible instead of hiding waiting time in the math.",
            "다음 일정 시작 시간이 실제로 가능하도록, 대기 시간을 숨기지 않고 일정 안에 드러냈습니다.",
        ),
        "expectedExperience": _copy(
            language,
            "Use this block for rest, photos, or a short browse instead of treating it like dead air.",
            "이 시간은 죽은 공백이 아니라 쉬거나 사진을 찍고, 잠깐 둘러보는 실제 여유 시간으로 쓸 수 있습니다.",
        ),
        "editableReason": _copy(
            language,
            "If you want a denser or looser day, this is the easiest block to trim or expand.",
            "일정을 더 촘촘하게 혹은 더 느슨하게 조정하고 싶다면 가장 먼저 손보기 쉬운 구간입니다.",
        ),
        "restBufferReason": gap_reason,
        "isNightViewSpot": False,
        "energy_level": 1,
        "route_to_next": None,
    }


def _gap_title(anchor_item: dict[str, Any], duration: int, preference_profile: dict[str, Any], language: str) -> str:
    role = _role_key(anchor_item)
    if role == "night_view":
        return _copy(
            language,
            "Sunset stroll and photo time" if duration >= 60 else "Sunset buffer",
            "해질녘 산책과 사진 시간" if duration >= 60 else "석양 대기 시간",
        )
    if role == "restaurant" and _is_lunch_item(anchor_item):
        return _copy(
            language,
            "Cafe break before lunch" if duration >= 60 else "Free time before lunch",
            "점심 전 카페와 산책" if duration >= 60 else "점심 전 자유 시간",
        )
    if role == "restaurant":
        return _copy(
            language,
            "Reset before dinner" if duration >= 60 else "Easy stroll before dinner",
            "저녁 전 재정비와 카페 휴식" if duration >= 60 else "저녁 전 여유 산책",
        )
    if preference_profile.get("slow"):
        return _copy(language, "Slow cafe break", "천천히 쉬는 카페 시간")
    if duration >= 120:
        return _copy(language, "Hotel reset or check-in", "호텔 체크인·재정비")
    return _copy(language, "Photo and browse time", "사진과 둘러보기 시간")


def _gap_reason(anchor_item: dict[str, Any], duration: int, preference_profile: dict[str, Any], language: str) -> str:
    role = _role_key(anchor_item)
    place_name = str((anchor_item.get("place") or {}).get("name") or anchor_item.get("title") or "").strip()
    if role == "night_view":
        return _copy(
            language,
            f"This block keeps arrival to {place_name} in the evening window, so the time before it works as a real sunset stroll instead of dead air.",
            f"{place_name}을 너무 이르게 소비하지 않도록, 이 구간은 해질녘 산책과 사진 시간을 확보하는 용도로 남겨 둔 블록입니다.",
        )
    if role == "restaurant" and _is_lunch_item(anchor_item):
        return _copy(
            language,
            "The route reaches lunch with enough margin that this block works better as a visible cafe or browse stop than as hidden idle time.",
            "점심 시간보다 조금 일찍 도착하는 흐름이라, 보이지 않는 공백 대신 카페나 가벼운 산책으로 쓸 수 있는 여유 블록으로 남겼습니다.",
        )
    if role == "restaurant":
        return _copy(
            language,
            "This keeps dinner at a natural hour and gives the afternoon a lived-in pause instead of forcing the next move too early.",
            "오후 일정을 억지로 늘이지 않고, 저녁 식사 전 카페 휴식이나 재정비로 쓰기 좋은 실제 여유 구간입니다.",
        )
    if preference_profile.get("slow"):
        return _copy(
            language,
            "Slow pace works better when breathing room turns into a named break instead of disappearing between stops.",
            "slow pace 일정에서는 이런 시간이 사라진 공백보다 이름 있는 휴식 블록으로 보일 때 흐름이 더 자연스럽습니다.",
        )
    if duration >= 120:
        return _copy(
            language,
            "This longer pause is best used for hotel reset, photos, or a nearby browse before the next fixed-time stop.",
            "다음 고정 시간대 전까지 생기는 긴 여유라, 호텔 재정비나 사진·가벼운 둘러보기 시간으로 쓰는 편이 자연스럽습니다.",
        )
    return _copy(
        language,
        "This visible break keeps the timeline feasible without pretending the time disappears.",
        "시간표가 실제로 가능하도록, 사라진 시간처럼 숨기지 않고 드러낸 여유 블록입니다.",
    )


def _time_slot_for_minutes(minutes: int) -> str:
    if minutes < 12 * 60:
        return "morning"
    if minutes < 14 * 60:
        return "lunch"
    if minutes < 18 * 60:
        return "afternoon"
    return "evening"


def _role_label(role: str, item: dict[str, Any], language: str) -> str:
    if role == "gap":
        return _copy(language, "Recommended buffer", "추천 여유 시간")
    if role == "meal_placeholder":
        return _copy(language, "Meal choice needed", "식사 후보 필요")
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
        "gap": "⏳",
        "meal_placeholder": "🍽",
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


def _meal_description(
    meal_type: str,
    language: str,
    preference_profile: dict[str, Any],
    next_stop: dict[str, Any] | None = None,
) -> str:
    next_role = _role_key(next_stop) if isinstance(next_stop, dict) else ""
    if language == "en":
        if meal_type == "dinner" and preference_profile.get("night_view") and next_role == "night_view":
            return "Dinner is placed close to the evening view so you can move into the night scene without another hard transfer."
        if meal_type == "lunch" and preference_profile.get("slow"):
            return "Lunch is used as a real recovery block so the afternoon can continue at an unhurried pace."
        if meal_type == "lunch":
            return "Lunch lands after the first focused block so the route can reset before the afternoon."
        return "This meal stop is positioned to connect the surrounding places without breaking the rhythm of the day."

    if meal_type == "dinner" and preference_profile.get("night_view") and next_role == "night_view":
        return "저녁 식사 뒤 바로 야경 포인트로 넘어가도록 잡아, 식사와 밤 장면이 따로 놀지 않게 묶은 구간입니다."
    if meal_type == "lunch" and preference_profile.get("slow"):
        return "slow pace를 반영해 점심을 단순 끼니가 아니라 앉아서 회복하는 휴식 블록처럼 배치했습니다."
    if meal_type == "lunch":
        return "오전 집중 구간 뒤에 점심을 넣어 오후 일정으로 넘어가기 전에 리듬을 다시 정리할 수 있게 했습니다."
    return "앞뒤 장소가 무리 없이 이어지도록 동선 안쪽에서 고른 식사 구간입니다."


def _meal_anchor(items: list[dict[str, Any]], start_index: int) -> dict[str, float]:
    origin = _coordinates(items[start_index])
    if start_index + 1 < len(items):
        return midpoint(origin, _coordinates(items[start_index + 1]))
    return origin


def _apply_day_theme(
    day: dict[str, Any],
    language: str,
    preference_profile: dict[str, Any],
    day_index: int,
    total_days: int,
) -> None:
    items = [dict(item) for item in day.get("items") or []]
    if not items:
        return
    existing_title = str(day.get("dayTheme") or day.get("title") or "").strip()
    existing_archetype = str(day.get("blueprintArchetype") or day.get("dayArchetype") or "").strip()
    if existing_title and not _looks_generic_day_title(existing_title) and (
        bool(existing_archetype) or _title_matches_selected_places(existing_title, items)
    ):
        title = existing_title
    else:
        title = _day_theme_title(int(day.get("day_number") or 1), items, language, preference_profile, day_index, total_days)
    day["theme"] = title
    day["dayTheme"] = title
    day["title"] = title


def _looks_generic_day_title(title: str) -> bool:
    compact = title.strip().lower()
    generic_tokens = (
        "사람답게",
        "핵심 코스",
        "클래식 파리와 야경",
        "예술과 명소를 천천히",
        "카페 거리와 로컬 산책",
        "쇼핑과 카페를 곁들인",
        "초록 쉼표",
        "paris highlights with a human pace",
        "art, icons & slow looking",
        "classic paris with an evening view",
        "cafe streets & local walks",
        "shopping, cafes & easy wandering",
        "green breaks between paris highlights",
    )
    return any(token in compact for token in generic_tokens)


def _title_matches_selected_places(title: str, items: list[dict[str, Any]]) -> bool:
    compact_title = title.lower()
    item_names = " ".join(
        str((item.get("place") or {}).get("name") or item.get("title") or "").lower()
        for item in items
        if item.get("itemKind") != "gap"
    )
    signature_groups = (
        ("에펠", "eiffel"),
        ("센강", "seine"),
        ("몽마르트", "montmartre"),
        ("샹젤", "champs"),
        ("개선문", "arc de triomphe"),
        ("루브르", "louvre"),
        ("오르세", "orsay"),
        ("노트르담", "notre-dame"),
        ("마레", "marais"),
    )
    for korean_token, english_token in signature_groups:
        if korean_token in title or english_token in compact_title:
            if korean_token not in item_names and english_token not in item_names:
                return False
    return True


def _day_theme_title(
    day_number: int,
    items: list[dict[str, Any]],
    language: str,
    preference_profile: dict[str, Any],
    day_index: int,
    total_days: int,
) -> str:
    stops = [item for item in items if item.get("itemKind") != "gap" and not item.get("nearbyMealNeeded")]
    roles = [_role_key(item) for item in stops]
    names = [str((item.get("place") or {}).get("name") or item.get("title") or "").strip() for item in stops]
    first_name = names[0] if names else _copy(language, "Paris", "파리")
    last_name = names[-1] if names else _copy(language, "Paris", "파리")
    museum_name = next((name for item, name in zip(stops, names) if _role_key(item) == "museum"), "")
    night_name = next((name for item, name in zip(stops, names) if _role_key(item) == "night_view"), "")
    walk_name = next((name for item, name in zip(stops, names) if _role_key(item) in {"park", "neighborhood", "cafe"}), "")
    lowercase_names = " ".join(names).lower()

    if language == "en":
        if preference_profile.get("night_view") and day_index == 0 and night_name:
            theme = f"Ease into Paris with {first_name} and a closing {night_name} night view"
        elif museum_name and walk_name:
            theme = f"An art-led day from {museum_name} into {walk_name}"
        elif "montmartre" in lowercase_names:
            theme = "A slow Montmartre day of stairs, cafes, and sunset atmosphere"
        elif "arc de triomphe" in lowercase_names and "champs" in lowercase_names:
            theme = "A classic Paris walk from the Arc de Triomphe to the Champs-Elysees"
        elif day_index == total_days - 1 and preference_profile.get("slow"):
            theme = f"A final Paris stroll that leaves room for {last_name}"
        else:
            theme = f"A Paris day flowing from {first_name} to {last_name}"
        return f"Day {day_number} - {theme}"

    if preference_profile.get("night_view") and day_index == 0 and night_name:
        lead_name = walk_name or first_name
        theme = f"파리 첫날, {lead_name}과 {night_name} 야경에 천천히 스며드는 하루"
    elif museum_name and walk_name:
        theme = f"{museum_name}과 {walk_name}으로 이어지는 예술의 하루"
    elif "montmartre" in lowercase_names or "몽마르트" in lowercase_names:
        theme = "몽마르트르 골목과 카페 감성을 따라 걷는 하루"
    elif "arc de triomphe" in lowercase_names or "개선문" in lowercase_names:
        if "champs" in lowercase_names or "샹젤리제" in lowercase_names:
            theme = "개선문에서 샹젤리제까지, 클래식 파리를 걷는 하루"
        else:
            theme = f"개선문과 {last_name}을 잇는 클래식 파리의 하루"
    elif day_index == total_days - 1 and preference_profile.get("slow"):
        theme = f"마지막 날, {last_name}까지 천천히 여운을 남기는 하루"
    elif night_name:
        theme = f"{first_name}에서 {night_name} 야경으로 이어지는 하루"
    elif "museum" in roles or "gallery" in roles:
        theme = f"{museum_name or first_name} 중심으로 천천히 감상하는 하루"
    else:
        theme = f"{first_name}에서 {last_name}까지 파리의 흐름을 따라 걷는 하루"
    return f"Day {day_number} - {theme}"


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
    highlights = [
        str(item.get("title") or "")
        for item in items
        if item.get("itemKind") != "gap" and not item.get("nearbyMealNeeded") and str(item.get("title") or "").strip()
    ]
    lead = ", ".join(highlights[:3])
    effort_levels = [
        str((item.get("route_to_next") or {}).get("effort_level") or "")
        for item in items
        if isinstance(item.get("route_to_next"), dict)
    ]
    high_burden_count = sum(1 for level in effort_levels if level == "high")
    if effort_levels and all(level == "low" for level in effort_levels):
        effort_copy = _copy(language, "low movement pressure", "이동 부담이 낮은 편")
    elif high_burden_count > 1:
        effort_copy = _copy(language, "more than one heavier transfer remains visible", "긴 이동이 2구간 이상 남아 있음")
    elif "high" in effort_levels:
        effort_copy = _copy(language, "one heavier transfer is included", "긴 이동 한 구간이 포함됨")
    else:
        effort_copy = _copy(language, "movement stays moderate", "이동 부담이 과하지 않음")

    mode_label = {
        "walk": _copy(language, "mostly on foot", "도보 위주"),
        "transit": _copy(language, "mostly by transit", "대중교통 위주"),
        "mixed": _copy(language, "with short walks and transit", "짧은 도보와 대중교통을 섞어"),
    }[route_mode]
    return _copy(
        language,
        f"The day links {lead} {mode_label}, and the route keeps {effort_copy}.",
        f"{lead} 중심으로 {mode_label} 연결했고, 전체적으로 {effort_copy}로 정리했습니다.",
    )


def _enrich_day_story(
    day: dict[str, Any],
    items: list[dict[str, Any]],
    route_mode: RouteMode,
    preference_profile: dict[str, Any],
    language: str,
) -> None:
    route_summary = _day_route_summary(items, route_mode, language)
    existing_route_summary = str(day.get("routeSummary") or day.get("route_summary") or "").strip()
    existing_day_summary = str(day.get("daySummary") or "").strip()
    route_summary = existing_route_summary if existing_route_summary and len(existing_route_summary) >= len(route_summary) - 8 else route_summary
    day["route_summary"] = route_summary
    day["routeSummary"] = route_summary
    generated_day_summary = _day_summary(day, items, preference_profile, language)
    day["daySummary"] = existing_day_summary if existing_day_summary and len(existing_day_summary) >= len(generated_day_summary) - 8 else generated_day_summary


def _day_summary(day: dict[str, Any], items: list[dict[str, Any]], preference_profile: dict[str, Any], language: str) -> str:
    highlights = [
        str(item.get("title") or "")
        for item in items
        if item.get("itemKind") != "gap" and not item.get("nearbyMealNeeded") and str(item.get("title") or "").strip()
    ]
    core_names = ", ".join(highlights[:3])
    high_burden_count = sum(
        1
        for item in items
        if isinstance(item.get("route_to_next"), dict) and str((item.get("route_to_next") or {}).get("effort_level") or "") == "high"
    )
    if language == "en":
        lines: list[str] = []
        if preference_profile.get("night_view") and any(item.get("isNightViewSpot") for item in items):
            lines.append("Night-view preferences lead the second half of the day toward a stronger evening payoff.")
        if preference_profile.get("slow"):
            lines.append("The pace stays intentionally loose, with buffers for sitting down and walking without rush.")
        if preference_profile.get("slow") and high_burden_count > 1:
            lines.append("A couple of longer transfers remain, so those segments are surfaced explicitly for review.")
        if preference_profile.get("museum") and any(_role_key(item) == "museum" for item in items):
            lines.append("Museum-heavy stops are placed earlier while attention is fresher.")
        if not lines:
            lines.append(f"The day flows around {core_names} with a balanced Paris rhythm.")
        return " ".join(lines)

    lines = []
    if preference_profile.get("night_view") and any(item.get("isNightViewSpot") for item in items):
        lines.append("야경 취향을 반영해 후반부가 자연스럽게 빛이 살아나는 장소로 이어지도록 구성했습니다.")
    if preference_profile.get("slow"):
        lines.append("slow pace를 반영해 장소 수를 과하게 늘리지 않고, 앉아 쉬거나 산책으로 호흡을 고를 구간을 남겼습니다.")
    if preference_profile.get("slow") and high_burden_count > 1:
        lines.append("긴 이동이 두 번 이상 남는 날은 숨기지 않고 그대로 드러내 사용자가 쉽게 수정할 수 있게 했습니다.")
    if preference_profile.get("museum") and any(_role_key(item) == "museum" for item in items):
        lines.append("미술관은 집중력이 좋은 오전과 이른 오후에 두어 감상 흐름이 끊기지 않게 했습니다.")
    if not lines:
        lines.append(f"{core_names} 중심으로 하루 리듬이 무너지지 않도록 동선과 체류 시간을 묶었습니다.")
    return " ".join(lines)


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


def _slot_purpose(
    item: dict[str, Any],
    role: str,
    index: int,
    total_items: int,
    preference_profile: dict[str, Any],
    language: str,
) -> str:
    if language == "en":
        if role == "restaurant":
            return "A meal pause placed where the route can slow down without breaking momentum."
        if role == "museum":
            return "A focused culture block while attention is still high."
        if role in {"park", "neighborhood", "cafe"}:
            return "A breathing space that lets the day feel lived-in rather than checked off."
        if role == "night_view" or index == total_items - 1:
            return "The emotional closing scene of the day."
        return "A core Paris stop that keeps the story of the day coherent."

    if role == "restaurant":
        return "동선의 흐름을 끊지 않으면서도 충분히 쉬어갈 수 있는 식사 구간입니다."
    if role == "museum":
        return "집중력이 남아 있을 때 한 곳에 몰입하는 문화 감상 구간입니다."
    if role in {"park", "neighborhood", "cafe"}:
        return "체크리스트처럼 흘러가지 않도록 호흡을 늦추는 산책·휴식 구간입니다."
    if role == "night_view" or index == total_items - 1:
        return "하루의 감정선을 정리하는 마지막 하이라이트 구간입니다."
    return "그날의 핵심 분위기를 만드는 대표 파리 스톱입니다."


def _user_preference_reason(item: dict[str, Any], role: str, preference_profile: dict[str, Any], language: str) -> str:
    place_name = str((item.get("place") or {}).get("name") or item.get("title") or "")
    if language == "en":
        if preference_profile.get("night_view") and (role == "night_view" or item.get("isNightViewSpot")):
            return f"Placed to match a night-view trip style so you reach {place_name} when the mood matters most."
        if preference_profile.get("slow") and role in {"park", "neighborhood", "cafe", "restaurant"}:
            return "Matched to a slower travel pace by reducing hard transitions and leaving room to sit and linger."
        if preference_profile.get("museum") and role == "museum":
            return "Chosen because your trip brief clearly leans toward museum-led Paris highlights."
        if preference_profile.get("local") and role in {"neighborhood", "park", "cafe"}:
            return "Keeps the day closer to street atmosphere and lived-in Paris scenes."
        return ""

    if preference_profile.get("night_view") and (role == "night_view" or item.get("isNightViewSpot")):
        return f"야경 여행 스타일에 맞춰 {place_name}의 분위기가 가장 살아나는 시간대로 당겼습니다."
    if preference_profile.get("slow") and role in {"park", "neighborhood", "cafe", "restaurant"}:
        return "slow 여행 속도에 맞춰 긴 이동을 줄이고, 머무는 시간이 자연스럽게 느껴지는 구간으로 잡았습니다."
    if preference_profile.get("museum") and role == "museum":
        return "미술관·예술 선호가 분명해서 대표 컬렉션에 시간을 깊게 쓰는 축으로 배치했습니다."
    if preference_profile.get("local") and role in {"neighborhood", "park", "cafe"}:
        return "로컬 산책 취향에 맞춰 관광 체크포인트보다 거리의 분위기를 체감하기 좋은 선택입니다."
    return ""


def _time_reason(
    item: dict[str, Any],
    role: str,
    index: int,
    total_items: int,
    preference_profile: dict[str, Any],
    language: str,
) -> str:
    slot = str(item.get("time_slot") or "")
    if language == "en":
        if role == "museum":
            return "Placed in the morning or early afternoon while focus is steadier."
        if role == "restaurant" and slot == "lunch":
            return "Inserted after the first high-focus block so the route can reset before the afternoon."
        if role == "night_view" or slot == "evening":
            return "Placed after sunset so the light and atmosphere feel intentional."
        if role in {"park", "neighborhood"} and slot == "afternoon":
            return "Afternoon light and energy make this easier to enjoy without rushing."
        if index == 0:
            return "Starts the day with a place that is easy to enter without decision fatigue."
        return "Timed to keep the day from spiking too early in effort."

    if role == "museum":
        return "미술관은 집중력이 좋은 오전이나 이른 오후에 두어 작품 감상 피로를 줄였습니다."
    if role == "restaurant" and slot == "lunch":
        return "오전 집중 구간 뒤에 점심을 넣어 오후 전환이 자연스럽게 이어지도록 했습니다."
    if role == "night_view" or slot == "evening":
        return "야경·석양 타이밍이 살아나는 저녁 이후 시간대에 맞춰 배치했습니다."
    if role in {"park", "neighborhood"} and slot == "afternoon":
        return "빛이 부드럽고 걷기 편한 오후로 두어 사진과 산책 만족도를 높였습니다."
    if index == 0:
        return "하루 초반 결정 피로가 적은 첫 스톱으로 두어 리듬을 부드럽게 열었습니다."
    return "이전 구간의 에너지 소모를 고려해 무리 없이 이어질 시간대로 정렬했습니다."


def _expected_experience(item: dict[str, Any], role: str, language: str) -> str:
    place_name = str((item.get("place") or {}).get("name") or item.get("title") or "")
    if language == "en":
        mapping = {
            "museum": f"Spend longer with the collection instead of grazing through {place_name}.",
            "night_view": f"Arrive with enough time to let {place_name} feel like the day's payoff.",
            "park": f"Use {place_name} as a reset instead of another hard sightseeing push.",
            "neighborhood": f"Let {place_name} work as a mood walk rather than a checklist stop.",
            "restaurant": "Take a real pause instead of a rushed convenience stop.",
            "cafe": "Slow down and sit long enough to recover energy.",
        }
        return mapping.get(role, f"Keep {place_name} memorable without overpacking the surrounding blocks.")

    mapping = {
        "museum": f"{place_name}에서 작품을 훑지 않고 한 호흡 길게 머무는 경험을 기대할 수 있습니다.",
        "night_view": f"{place_name}이 하루의 마지막 장면처럼 남도록 도착 시간을 잡았습니다.",
        "park": f"{place_name}을 체크포인트가 아니라 호흡을 회복하는 구간처럼 즐길 수 있습니다.",
        "neighborhood": f"{place_name}을 관광지 소비가 아니라 분위기를 걷는 시간으로 느끼기 좋습니다.",
        "restaurant": "허기만 채우는 식사가 아니라 다음 구간을 위한 진짜 휴식처럼 쓰게 됩니다.",
        "cafe": "잠깐 소비하는 카페가 아니라 앉아서 리듬을 되찾는 정지점이 됩니다.",
    }
    return mapping.get(role, f"{place_name}을 과하게 서두르지 않고 하루 맥락 안에서 자연스럽게 체감하도록 설계했습니다.")


def _editable_reason(item: dict[str, Any], role: str, language: str) -> str:
    slot = str(item.get("time_slot") or "")
    if language == "en":
        if role == "museum":
            return "This slot can be swapped with another museum or indoor highlight without breaking the day."
        if role == "night_view":
            return "This evening slot can be replaced with another night-view point while preserving the flow."
        if slot == "lunch":
            return "You can swap this meal with another nearby pick and keep the route stable."
        return "This stop can be exchanged with a nearby place of similar mood if your preference changes."

    if role == "museum":
        return "동선 전체를 무너뜨리지 않고 비슷한 성격의 미술관·실내 명소로 교체하기 쉬운 슬롯입니다."
    if role == "night_view":
        return "저녁 흐름은 유지한 채 다른 야경 포인트로 바꾸기 쉬운 슬롯입니다."
    if slot == "lunch":
        return "근처 식사 장소로 바꿔도 전체 리듬이 크게 흔들리지 않는 슬롯입니다."
    return "비슷한 분위기의 인근 장소로 미세 조정해도 하루 흐름을 유지하기 쉬운 구간입니다."
