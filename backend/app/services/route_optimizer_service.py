from __future__ import annotations

import re
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

DAY_START_MINUTES = 9 * 60 + 30
LUNCH_START_MINUTES = 12 * 60
DINNER_START_MINUTES = 18 * 60 + 15
EVENING_START_MINUTES = 18 * 60
GAP_DISCLOSURE_MINUTES = 15
DAY_END_MINUTES = 23 * 60 + 45
LATEST_STOP_START_MINUTES = 23 * 60
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
    low_walking = _low_walking_requested(brief, prompt=prompt, style_tags=style_tags)
    if low_walking and route_mode in {"walk", "mixed"}:
        route_mode = "transit"
    return {
        "night_view": bool(brief.get("night_view_required")) or any(token in haystack for token in ("night_view", "night", "view", "야경", "석양", "선셋")),
        "museum": any(token in haystack for token in ("museum", "art", "미술관", "박물관", "예술")),
        "local": any(token in haystack for token in ("local", "hidden_gems", "walk", "로컬", "골목", "산책")),
        "shopping": any(token in haystack for token in ("shopping", "쇼핑")),
        "foodie": any(token in haystack for token in ("foodie", "cafe", "맛집", "카페", "브런치")),
        "slow": pace_level == "slow",
        "fast": pace_level == "fast",
        "low_walking": low_walking,
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
    compact = _compact_source_text(haystack)
    if any(
        token in compact
        for token in (
            "lesswalking",
            "lowwalking",
            "avoidwalking",
            "notmuchwalking",
            "nolongwalks",
            "\ub9ce\uc774\uac77\uae30\uc2eb",
            "\ub9ce\uc774\uc548\uac77",
            "\ub3c4\ubcf4\ubd80\ub2f4",
            "\uac77\ub294\uac70\uc2eb",
            "\uc774\ub3d9\uac15\ub3c4\ub0ae",
        )
    ):
        return "transit"
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
        day["items"] = _trim_low_walking_items_after_schedule(day["items"], preference_profile)
        _apply_day_theme(day, language, preference_profile, day_index, total_days)
        _enrich_day_story(day, day["items"], route_mode, preference_profile, language)
    return route_mode


def _route_mode_from_brief(planning_brief: dict[str, Any]) -> RouteMode | None:
    if _low_walking_requested(planning_brief):
        return "transit"
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


def _low_walking_requested(
    planning_brief: dict[str, Any] | None,
    *,
    prompt: str = "",
    style_tags: list[Any] | None = None,
) -> bool:
    brief = planning_brief if isinstance(planning_brief, dict) else {}
    mobility = brief.get("mobility_constraints") if isinstance(brief.get("mobility_constraints"), dict) else {}
    if str(brief.get("walking_intensity") or mobility.get("walking_intensity") or "").lower() == "low":
        return True
    if bool(mobility.get("prefer_transit_between_areas")):
        return True
    text = " ".join(
        [
            prompt,
            str(brief.get("source_text") or ""),
            " ".join(str(tag) for tag in (style_tags or [])),
            " ".join(str(tag) for tag in brief.get("travel_style") or []),
            " ".join(str(value) for value in brief.get("must_avoid") or []),
        ]
    ).lower()
    compact = _compact_source_text(text)
    return any(
        token in compact
        for token in (
            "lesswalking",
            "lowwalking",
            "avoidwalking",
            "notmuchwalking",
            "nolongwalks",
            "\ub9ce\uc774\uac77\uae30\uc2eb",
            "\ub9ce\uc774\uac77\uc9c0",
            "\ub9ce\uc774\uc548\uac77",
            "\ub3c4\ubcf4\ubd80\ub2f4",
            "\uac77\ub294\uac70\uc2eb",
            "\uc774\ub3d9\uac15\ub3c4\ub0ae",
        )
    )


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
    original_items = await _ensure_brief_must_include_items(db, original_items, preference_profile, language, day_index, total_days)
    original_items = _compact_required_route_items(original_items, preference_profile)
    preserve_planner_story = bool(day.get("blueprintArchetype") or day.get("dayArchetype")) and _has_explicit_story_order(original_items)
    if preserve_planner_story:
        resolved_items: list[dict[str, Any]] = []
        for item in original_items:
            resolved = await _resolve_item_place(db, item) or dict(item)
            resolved_items.append(resolved)
        resolved_items = _dedupe_items_by_place(resolved_items)
        if not resolved_items:
            return
        resolved_items = await _ensure_requested_meal_anchors(
            db,
            resolved_items,
            language,
            preference_profile,
        )
        resolved_items = _ensure_requested_cafe_anchor(resolved_items, language, preference_profile)
        resolved_items = _apply_scoped_daypart_times(resolved_items, preference_profile)
        resolved_items = _apply_structured_place_constraints(resolved_items, preference_profile)
        resolved_items = _apply_explicit_source_order(resolved_items, preference_profile)
        resolved_items = _move_final_anchor_to_end(resolved_items, preference_profile)
        resolved_items = _apply_structured_place_constraints(resolved_items, preference_profile)
        resolved_items = _apply_explicit_source_order(resolved_items, preference_profile, keep_final=True)
        resolved_items = _drop_negative_night_tail_items(resolved_items, preference_profile)
        await _attach_route_legs(resolved_items, route_mode, language)
        day["items"] = _schedule_day(resolved_items, pace_level, language, preference_profile)
        day["items"] = await _repair_missing_required_after_schedule(
            db,
            day["items"],
            route_mode,
            pace_level,
            language,
            preference_profile,
            day_index,
            total_days,
        )
        day["items"] = _dedupe_items_by_place(day["items"])
        day["items"] = _trim_museum_limit_after_schedule(day["items"], preference_profile)
        day["items"] = _trim_slow_items_after_schedule(day["items"], preference_profile)
        day["items"] = _trim_relaxed_items_after_schedule(day["items"], preference_profile)
        day["items"] = _trim_low_walking_items_after_schedule(day["items"], preference_profile)
        day["items"] = _drop_items_after_final_anchor(day["items"], preference_profile)
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
    enriched_items = _ensure_requested_cafe_anchor(enriched_items, language, preference_profile)
    enriched_items = _apply_scoped_daypart_times(enriched_items, preference_profile)
    enriched_items = _apply_structured_place_constraints(enriched_items, preference_profile)
    enriched_items = _apply_explicit_source_order(enriched_items, preference_profile)
    enriched_items = _move_final_anchor_to_end(enriched_items, preference_profile)
    enriched_items = _apply_structured_place_constraints(enriched_items, preference_profile)
    enriched_items = _apply_explicit_source_order(enriched_items, preference_profile, keep_final=True)
    enriched_items = _drop_negative_night_tail_items(enriched_items, preference_profile)
    await _attach_route_legs(enriched_items, route_mode, language)
    day["items"] = _schedule_day(enriched_items, pace_level, language, preference_profile)
    day["items"] = await _repair_missing_required_after_schedule(
        db,
        day["items"],
        route_mode,
        pace_level,
        language,
        preference_profile,
        day_index,
        total_days,
    )
    day["items"] = _dedupe_items_by_place(day["items"])
    day["items"] = _trim_museum_limit_after_schedule(day["items"], preference_profile)
    day["items"] = _trim_slow_items_after_schedule(day["items"], preference_profile)
    day["items"] = _trim_relaxed_items_after_schedule(day["items"], preference_profile)
    day["items"] = _trim_low_walking_items_after_schedule(day["items"], preference_profile)
    day["items"] = _drop_items_after_final_anchor(day["items"], preference_profile)
    _apply_day_theme(day, language, preference_profile, day_index, total_days)
    _enrich_day_story(day, day["items"], route_mode, preference_profile, language)


async def _repair_missing_required_after_schedule(
    db: AsyncIOMotorDatabase,
    scheduled_items: list[dict[str, Any]],
    route_mode: RouteMode,
    pace_level: str,
    language: str,
    preference_profile: dict[str, Any],
    day_index: int | None = None,
    total_days: int | None = None,
) -> list[dict[str, Any]]:
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    if not isinstance(brief, dict):
        return scheduled_items
    constraints = [constraint for constraint in brief.get("place_constraints") or [] if isinstance(constraint, dict)]
    next_items = [dict(item) for item in scheduled_items]
    changed = False
    for target in [str(value) for value in brief.get("must_include") or [] if str(value).strip()]:
        constraint = next(
            (
                constraint
                for constraint in constraints
                if str(constraint.get("target") or "") == target
                or _compact_source_text(str(constraint.get("target") or "")) == _compact_source_text(target)
            ),
            {"target": target},
        )
        constraint = dict(constraint)
        if not str(constraint.get("canonical") or "").strip():
            inferred_canonical = _canonical_from_target_text(target)
            if inferred_canonical:
                constraint["canonical"] = inferred_canonical
        if not _must_include_repair_applies_to_day(constraint, day_index=day_index, total_days=total_days):
            continue
        if any(_item_matches_constraint(item, constraint) for item in next_items):
            continue
        if str(constraint.get("canonical") or "") == "champs" and _mark_arc_axis_as_champs(next_items):
            changed = True
            continue
        place = await _resolve_brief_target_place(db, target, constraint)
        if not place:
            continue
        slot = str(constraint.get("time_slot") or "").strip() or _default_slot_for_constraint(constraint)
        item = _item_from_resolved_place(place, slot=slot, language=language)
        item["slotLockReason"] = "brief_must_include_repair"
        next_items.append(item)
        changed = True
    if not changed:
        return scheduled_items

    next_items = _dedupe_items_by_place(next_items)
    next_items = _apply_structured_place_constraints(next_items, preference_profile)
    next_items = _move_final_anchor_to_end(next_items, preference_profile)
    next_items = _apply_structured_place_constraints(next_items, preference_profile)
    await _attach_route_legs(next_items, route_mode, language)
    return _schedule_day(next_items, pace_level, language, preference_profile)


def _must_include_repair_applies_to_day(
    constraint: dict[str, Any],
    *,
    day_index: int | None,
    total_days: int | None,
) -> bool:
    """Avoid injecting trip-level anchors into every day of a multi-day plan."""

    if not total_days or total_days <= 1 or day_index is None:
        return True
    explicit_day = _constraint_day_number(constraint)
    if explicit_day is not None:
        return explicit_day == day_index + 1
    if bool(constraint.get("final")):
        return day_index == total_days - 1
    return str(constraint.get("scope") or "").lower() == "daily"


def _constraint_day_number(constraint: dict[str, Any]) -> int | None:
    for key in ("target_day", "preferred_day", "day_number", "day"):
        raw = constraint.get(key)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def _mark_arc_axis_as_champs(items: list[dict[str, Any]]) -> bool:
    for item in items:
        if not _item_matches_constraint(item, {"canonical": "arc", "target": "Arc de Triomphe"}):
            continue
        place = item.setdefault("place", {})
        tags = list(place.get("tags") or [])
        for tag in ("champselysees", "champs-elysees", "\uc0f9\uc824\ub9ac\uc81c"):
            if tag not in tags:
                tags.append(tag)
        place["tags"] = tags
        item["routeAxisLabel"] = "Champs-Elysees"
        return True
    return False


def _trim_slow_items_after_schedule(
    items: list[dict[str, Any]],
    preference_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    if not isinstance(brief, dict) or str(brief.get("pace") or "").lower() != "slow":
        return items
    next_items = [dict(item) for item in items]
    hard_constraints = []
    for value in [str(value) for value in brief.get("must_include") or [] if str(value).strip()]:
        constraint = {"target": value}
        inferred_canonical = _canonical_from_target_text(value)
        if inferred_canonical:
            constraint["canonical"] = inferred_canonical
        hard_constraints.append(constraint)
    real_count = sum(1 for item in next_items if item.get("itemKind") != "gap")
    while real_count > 5:
        remove_index = None
        for index in range(len(next_items) - 1, -1, -1):
            item = next_items[index]
            if item.get("itemKind") == "gap" or item.get("finalAnchor"):
                continue
            if any(_item_matches_constraint(item, constraint) for constraint in hard_constraints):
                continue
            role = _role_key(item)
            if role in {"cafe", "restaurant"} and real_count <= 6:
                continue
            remove_index = index
            break
        if remove_index is None:
            break
        next_items.pop(remove_index)
        real_count = sum(1 for item in next_items if item.get("itemKind") != "gap")
    return next_items


def _trim_relaxed_items_after_schedule(
    items: list[dict[str, Any]],
    preference_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    if not isinstance(brief, dict) or str(brief.get("pace") or "").lower() == "fast":
        return items
    compact_source = _compact_source_text(str(brief.get("source_text") or ""))
    relaxed_signal = any(
        token in compact_source
        for token in (
            "\uac00\ubccd\uac8c",
            "\ud734\uc2dd",
            "\ud558\ub098",
            "\uc815\ub3c4",
            "\uc774\uba74\uc88b",
            "\uc788\uc73c\uba74\ub3fc",
            "\uc788\uc73c\uba74\ub418",
            "\uc801\uac8c",
            "relaxed",
        )
    )
    meal_preferences = {str(value).lower() for value in brief.get("meal_preference") or []}
    has_avoid = bool([value for value in brief.get("must_avoid") or [] if str(value).strip()])
    if not relaxed_signal and not (has_avoid and "cafe" in meal_preferences):
        return items
    return _trim_to_real_item_limit(items, preference_profile, limit=6)


def _trim_low_walking_items_after_schedule(
    items: list[dict[str, Any]],
    preference_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    if not preference_profile.get("low_walking"):
        return items
    next_items = [dict(item) for item in items]
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    hard_constraints = _hard_constraints_from_brief(brief if isinstance(brief, dict) else {})

    walk_like_indices = [
        index
        for index, item in enumerate(next_items)
        if item.get("itemKind") != "gap" and _is_walk_like_item(item, _role_key(item))
    ]
    while len(walk_like_indices) > 1:
        remove_index = None
        for index in reversed(walk_like_indices):
            item = next_items[index]
            if item.get("finalAnchor"):
                continue
            if any(_item_matches_constraint(item, constraint) for constraint in hard_constraints):
                continue
            remove_index = index
            break
        if remove_index is None:
            break
        next_items.pop(remove_index)
        walk_like_indices = [
            index
            for index, item in enumerate(next_items)
            if item.get("itemKind") != "gap" and _is_walk_like_item(item, _role_key(item))
        ]
    return next_items


def _trim_museum_limit_after_schedule(
    items: list[dict[str, Any]],
    preference_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    if not isinstance(brief, dict):
        return items
    try:
        museum_limit = int(brief.get("museum_limit_per_day") or 0)
    except (TypeError, ValueError):
        museum_limit = 0
    compact_source = _compact_source_text(str(brief.get("source_text") or ""))
    if not museum_limit and not any(
        token in compact_source
        for token in (
            "\ubc15\ubb3c\uad00\uc740\uc801\uac8c",
            "\ubbf8\uc220\uad00\uc740\uc801\uac8c",
            "\ubc15\ubb3c\uad00\uc801\uac8c",
            "\ubbf8\uc220\uad00\uc801\uac8c",
            "\ubc15\ubb3c\uad00\uc740\ud558\ub098\uc774\ud558",
            "\ubbf8\uc220\uad00\uc740\ud558\ub098\uc774\ud558",
            "\ubc15\ubb3c\uad00\ud558\ub098\uc774\ud558",
            "\ubbf8\uc220\uad00\ud558\ub098\uc774\ud558",
            "\ubc15\ubb3c\uad001\uac1c\uc774\ud558",
            "\ubbf8\uc220\uad001\uac1c\uc774\ud558",
            "\ub300\ud45c\ud558\ub098\ub9cc",
            "\ud558\ub098\ub9cc\ubcf4",
            "museumlimit",
        )
    ):
        return items
    museum_limit = museum_limit or 1
    hard_constraints = _hard_constraints_from_brief(brief)
    kept_museum_count = 0
    trimmed: list[dict[str, Any]] = []
    for item in items:
        if item.get("itemKind") == "gap" or _role_key(item) != "museum":
            trimmed.append(item)
            continue
        if any(_item_matches_constraint(item, constraint) for constraint in hard_constraints):
            kept_museum_count += 1
            trimmed.append(item)
            continue
        if kept_museum_count < museum_limit:
            kept_museum_count += 1
            trimmed.append(item)
    return trimmed


def _trim_to_real_item_limit(
    items: list[dict[str, Any]],
    preference_profile: dict[str, Any],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    hard_constraints = _hard_constraints_from_brief(brief if isinstance(brief, dict) else {})
    next_items = [dict(item) for item in items]
    while sum(1 for item in next_items if item.get("itemKind") != "gap") > limit:
        remove_index = None
        for index in range(len(next_items) - 1, -1, -1):
            item = next_items[index]
            if item.get("itemKind") == "gap" or item.get("finalAnchor"):
                continue
            if any(_item_matches_constraint(item, constraint) for constraint in hard_constraints):
                continue
            remove_index = index
            break
        if remove_index is None:
            break
        next_items.pop(remove_index)
    return next_items


def _hard_constraints_from_brief(brief: dict[str, Any]) -> list[dict[str, Any]]:
    hard_constraints = []
    constraints = [constraint for constraint in brief.get("place_constraints") or [] if isinstance(constraint, dict)]
    for value in [str(value) for value in brief.get("must_include") or [] if str(value).strip()]:
        constraint = next(
            (
                constraint
                for constraint in constraints
                if str(constraint.get("target") or "") == value
                or _compact_source_text(str(constraint.get("target") or "")) == _compact_source_text(value)
            ),
            {"target": value},
        )
        constraint = dict(constraint)
        inferred_canonical = _canonical_from_target_text(value)
        if inferred_canonical:
            constraint["canonical"] = inferred_canonical
        hard_constraints.append(constraint)
    return hard_constraints


def _drop_items_after_final_anchor(
    items: list[dict[str, Any]],
    preference_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    if not isinstance(brief, dict):
        return items
    final_target = str(brief.get("final_anchor") or "").strip()
    if not final_target:
        return items
    final_constraint = {"target": final_target}
    inferred_canonical = _canonical_from_target_text(final_target)
    if inferred_canonical:
        final_constraint["canonical"] = inferred_canonical
    final_index = next(
        (
            index
            for index, item in enumerate(items)
            if item.get("itemKind") != "gap"
            and (item.get("finalAnchor") or str(item.get("slotLockReason") or "") in {"structured_final_anchor", "final_night_anchor"} or _item_matches_constraint(item, final_constraint))
        ),
        None,
    )
    if final_index is None or final_index == len(items) - 1:
        return items
    hard_constraints = _hard_constraints_from_brief(brief)
    final_item = items[final_index]
    before_final = list(items[:final_index])
    hard_tail: list[dict[str, Any]] = []
    for item in items[final_index + 1 :]:
        if item.get("itemKind") == "gap":
            continue
        if any(_item_matches_constraint(item, constraint) for constraint in hard_constraints):
            hard_tail.append(item)
    return [*before_final, *hard_tail, final_item]


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
    resolved_item["place"] = _merge_place_metadata(place, resolved_place, coordinates=coordinates)
    resolved_item["title"] = resolved_place.get("name") or resolved_item.get("title") or name
    return resolved_item


def _merge_place_metadata(
    original: dict[str, Any],
    resolved: dict[str, Any],
    *,
    coordinates: dict[str, Any],
) -> dict[str, Any]:
    merged = {**resolved}
    for key, value in original.items():
        if value not in (None, "", [], {}):
            merged[key] = value
    merged["coordinates"] = coordinates
    return merged


async def _ensure_brief_must_include_items(
    db: AsyncIOMotorDatabase,
    items: list[dict[str, Any]],
    preference_profile: dict[str, Any],
    language: str,
    day_index: int | None = None,
    total_days: int | None = None,
) -> list[dict[str, Any]]:
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    if not isinstance(brief, dict):
        return items
    next_items = list(items)
    changed = False
    constraints = [constraint for constraint in brief.get("place_constraints") or [] if isinstance(constraint, dict)]
    for target in [str(value) for value in brief.get("must_include") or [] if str(value).strip()]:
        constraint = next(
            (
                constraint
                for constraint in constraints
                if str(constraint.get("target") or "") == target
                or _compact_source_text(str(constraint.get("target") or "")) == _compact_source_text(target)
            ),
            {"target": target},
        )
        constraint = dict(constraint)
        if not str(constraint.get("canonical") or "").strip():
            inferred_canonical = _canonical_from_target_text(target)
            if inferred_canonical:
                constraint["canonical"] = inferred_canonical
        if not _must_include_repair_applies_to_day(constraint, day_index=day_index, total_days=total_days):
            continue
        if any(_item_matches_constraint(item, constraint) for item in next_items):
            continue
        place = await _resolve_brief_target_place(db, target, constraint)
        if not place:
            continue
        slot = str(constraint.get("time_slot") or "").strip() or _default_slot_for_constraint(constraint)
        next_items.append(_item_from_resolved_place(place, slot=slot, language=language))
        changed = True
    if not changed:
        return next_items
    return sorted(
        next_items,
        key=lambda item: (
            _parse_clock_minutes(item.get("start_time")) is None,
            _parse_clock_minutes(item.get("start_time")) or 0,
            0 if item.get("slotLockReason") else 1,
        ),
    )


def _compact_required_route_items(items: list[dict[str, Any]], preference_profile: dict[str, Any]) -> list[dict[str, Any]]:
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    if not isinstance(brief, dict):
        return items
    compact_source = _compact_source_text(str(brief.get("source_text") or ""))
    if any(
        token in compact_source
        for token in (
            "\uac77\ub294\ucf54\uc2a4",
            "\ubb34\ub9ac\uc5c6\ub294\ub3d9\uc120",
            "\ub3d9\uc120",
            "\ub3c4\ubcf4",
            "\uac78\uc5b4",
        )
    ):
        compact_source = f"{compact_source}routecompact"
    if not any(token in compact_source for token in ("걷는코스", "무리없는동선", "동선", "도보", "routecompact", "walkingroute")):
        return items
    constraints = [constraint for constraint in brief.get("place_constraints") or [] if isinstance(constraint, dict)]
    required = [str(value) for value in brief.get("must_include") or [] if str(value).strip()]
    if len(required) < 2:
        return items
    kept: list[dict[str, Any]] = []
    for item in items:
        if any(
            _item_matches_constraint(
                item,
                next(
                    (
                        constraint
                        for constraint in constraints
                        if str(constraint.get("target") or "") == target
                        or _compact_source_text(str(constraint.get("target") or "")) == _compact_source_text(target)
                    ),
                    {"target": target},
                ),
            )
            for target in required
        ):
            kept.append(item)
    if len(kept) >= 2:
        return kept
    return items


async def _resolve_brief_target_place(
    db: AsyncIOMotorDatabase,
    target: str,
    constraint: dict[str, Any],
) -> dict[str, Any] | None:
    queries: list[str] = []
    canonical = str(constraint.get("canonical") or "").strip()
    queries.append(target)
    if canonical in _SCOPED_DAYPART_ALIASES:
        queries.extend(_SCOPED_DAYPART_ALIASES[canonical])
    for query in dict.fromkeys(queries):
        try:
            from parser_api.services.place_catalog import resolve_place as resolve_catalog_place

            catalog_place = resolve_catalog_place(query)
        except Exception:
            catalog_place = None
        if isinstance(catalog_place, dict):
            return catalog_place
        try:
            place = await resolve_place(db, query, fallback_coordinates=PARIS_CENTER)
        except Exception:
            place = None
        if isinstance(place, dict) and place.get("coordinates"):
            return place
    return None


def _canonical_from_target_text(target: str) -> str | None:
    compact = _compact_source_text(target)
    if not compact:
        return None
    for canonical, aliases in _SCOPED_DAYPART_ALIASES.items():
        if any((alias_value := _compact_source_text(alias)) and alias_value in compact for alias in aliases):
            return canonical
    return None


def _item_from_resolved_place(place: dict[str, Any], *, slot: str, language: str) -> dict[str, Any]:
    normalized_slot = "evening" if slot == "night" else slot if slot in _STRUCTURED_SLOT_MINUTES else "afternoon"
    minutes = _STRUCTURED_SLOT_MINUTES.get(slot, _STRUCTURED_SLOT_MINUTES.get(normalized_slot, 13 * 60 + 30))
    return {
        "id": str(uuid4()),
        "itemKind": "stop",
        "title": place.get("name") or "Paris stop",
        "time_slot": normalized_slot,
        "start_time": _format_clock(minutes),
        "place": {
            "place_id": place.get("slug") or place.get("place_id"),
            "slug": place.get("slug") or place.get("place_id"),
            "name": place.get("name") or "Paris stop",
            "category": place.get("category") or "landmark",
            "coordinates": place.get("coordinates") or PARIS_CENTER,
            "cuisine": place.get("cuisine"),
            "rating": place.get("rating"),
            "review_count": place.get("review_count"),
        },
        "description": place.get("short_description") or "Added by the Agent to satisfy a required stop.",
        "estimated_duration": place.get("estimated_visit_duration") or _format_duration_minutes(75, language),
        "slotLockReason": "brief_must_include_anchor",
        "slotTags": ["must_include"],
    }


def _default_slot_for_constraint(constraint: dict[str, Any]) -> str:
    canonical = str(constraint.get("canonical") or "")
    if canonical in {"seine", "eiffel", "arc", "jazz"}:
        return "evening"
    if canonical in {"louvre", "orsay", "notre", "sainte"}:
        return "morning"
    return "afternoon"


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
    place_id = str(place.get("place_id") or place.get("slug") or "").strip().lower()
    if place_id:
        keys.add(f"id:{place_id}")
    name = str(place.get("name") or item.get("title") or "").strip().lower()
    if name:
        keys.add(f"name:{name}")
    category = str(place.get("category") or "").lower()
    if category not in MEAL_PLACE_CATEGORIES:
        item_text = _compact_source_text(
            " ".join(
                [
                    str(item.get("title") or ""),
                    str(place.get("name") or ""),
                    str(place.get("slug") or place.get("place_id") or ""),
                ]
            )
        )
        for canonical, aliases in _SCOPED_DAYPART_ALIASES.items():
            if canonical == "arc" and "arcdetriomphe" not in item_text:
                continue
            if canonical == "garnier" and "garnier" not in item_text and "palaisgarnier" not in item_text:
                continue
            if any((alias := _compact_source_text(alias_value)) and alias in item_text for alias_value in aliases):
                keys.add(f"canonical:{canonical}")
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
    if role in {"cafe", "restaurant", "meal_placeholder"} and _is_lunch_item(item) and start_minutes < 15 * 60:
        if _is_brunch_item(item) and start_minutes < 12 * 60:
            return "morning"
        return "lunch"
    if role in {"restaurant", "meal_placeholder"}:
        if _is_lunch_item(item) and _is_brunch_item(item) and start_minutes < 12 * 60:
            return "morning"
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


async def _ensure_requested_meal_anchors(
    db: AsyncIOMotorDatabase,
    items: list[dict[str, Any]],
    language: str,
    preference_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    if not items:
        return items

    used_names = {str(item.get("place", {}).get("name") or item.get("title") or "").lower() for item in items}

    if _prefers_general_meal(preference_profile) and not _has_restaurant_anchor(items):
        anchor = _meal_anchor(items, min(1, len(items) - 1))
        lunch = await _meal_item(db, anchor, "lunch", language, used_names)
        if lunch:
            lunch = dict(lunch)
            if lunch.get("nearbyMealNeeded") or str((lunch.get("place") or {}).get("category") or "") == "meal_placeholder":
                lunch["place"] = {
                    "name": "Paris neighborhood restaurant",
                    "category": "restaurant",
                    "cuisine": ["french", "bistro"],
                    "coordinates": dict(anchor),
                    "tags": ["restaurant", "lunch"],
                }
                lunch["title"] = _copy(language, "Paris neighborhood restaurant lunch", "Paris neighborhood restaurant lunch")
            lunch["time_slot"] = "lunch"
            lunch["start_time"] = str(lunch.get("start_time") or "12:30")
            lunch["description"] = _meal_description(
                "lunch",
                language,
                preference_profile,
                next_stop=items[min(1, len(items) - 1)] if items else None,
            )
            insert_index = min(max(1, len(items) // 2), len(items))
            items = [*items[:insert_index], lunch, *items[insert_index:]]
            used_names.add(str((lunch.get("place") or {}).get("name") or lunch.get("title") or "").lower())

    if not _prefers_french_dinner(preference_profile) or _has_evening_meal(items):
        return items

    anchor = _meal_anchor(items, max(0, len(items) - 2))
    dinner = await _meal_item(db, anchor, "dinner", language, used_names)
    if not dinner:
        return items

    dinner = dict(dinner)
    if dinner.get("nearbyMealNeeded") or str((dinner.get("place") or {}).get("category") or "") == "meal_placeholder":
        dinner = _fallback_french_dinner_item(anchor, language)
    place_name = str((dinner.get("place") or {}).get("name") or dinner.get("title") or "").strip()
    if place_name and not _is_dinner_item(dinner):
        dinner["title"] = _copy(language, f"{place_name} dinner", f"{place_name} 저녁")
    dinner["description"] = _meal_description("dinner", language, preference_profile, next_stop=items[-1] if len(items) > 1 else None)
    dinner["time_slot"] = "evening"
    dinner["start_time"] = str(dinner.get("start_time") or "18:35")
    insert_index = max(1, len(items) - 1)
    return [*items[:insert_index], dinner, *items[insert_index:]]


def _ensure_requested_cafe_anchor(
    items: list[dict[str, Any]],
    language: str,
    preference_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    if not items or not _prefers_cafe_break(preference_profile):
        return items
    if any(_role_key(item) == "cafe" for item in items):
        if _afternoon_cafe_requested(preference_profile) and not any(
            _role_key(item) == "cafe" and str(item.get("time_slot") or "") == "afternoon"
            for item in items
        ):
            adjusted = [dict(item) for item in items]
            for item in adjusted:
                if _role_key(item) == "cafe":
                    item["time_slot"] = "afternoon"
                    item["start_time"] = "15:05"
                    item["slotLockReason"] = "requested_cafe_time"
                    break
            return adjusted
        return items

    anchor_index = 0 if len(items) == 1 else min(1, len(items) - 1)
    anchor = _coordinates(items[anchor_index])
    cafe = {
        "id": str(uuid4()),
        "time_slot": "afternoon",
        "start_time": "15:05",
        "title": _copy(language, "Paris cafe stop", "파리 카페 타임"),
        "place": {
            "name": _copy(language, "Paris cafe stop", "파리 카페 타임"),
            "category": "cafe",
            "cuisine": ["cafe", "coffee"],
            "coordinates": dict(anchor),
            "tags": ["cafe", "coffee", "relax"],
        },
        "description": _copy(
            language,
            "A cafe pause added because the user explicitly asked for cafe time.",
            "사용자가 카페 시간을 요청해 동선 중간에 넣은 휴식형 카페 구간입니다.",
        ),
        "estimated_duration": _copy(language, "1 hour", "1시간"),
        "slotTags": ["cafe", "coffee", "relax"],
    }
    insert_at = min(len(items), anchor_index + 1)
    return [*items[:insert_at], cafe, *items[insert_at:]]


def _afternoon_cafe_requested(preference_profile: dict[str, Any]) -> bool:
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    if "afternoon" not in {str(value) for value in (brief or {}).get("preferred_time_slots") or []}:
        return False
    compact = _compact_source_text(str((brief or {}).get("source_text") or ""))
    return any(token in compact for token in ("\uc624\ud6c4\uce74\ud398", "\uce74\ud398\uc640\uc0b0\ucc45", "afternooncafe"))


def _prefers_cafe_break(preference_profile: dict[str, Any]) -> bool:
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    meal_preferences = {str(value).lower() for value in (brief or {}).get("meal_preference") or []}
    style_tags = {str(value).lower() for value in preference_profile.get("style_tags") or []} if isinstance(preference_profile, dict) else set()
    return bool(meal_preferences.intersection({"cafe", "coffee", "dessert", "bakery", "brunch"})) or bool(style_tags.intersection({"cafe", "foodie", "dessert"}))


def _prefers_general_meal(preference_profile: dict[str, Any]) -> bool:
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    meal_preferences = {str(value).lower() for value in (brief or {}).get("meal_preference") or []}
    style_tags = {str(value).lower() for value in preference_profile.get("style_tags") or []} if isinstance(preference_profile, dict) else set()
    return bool(meal_preferences.intersection({"meal_preference", "meal", "restaurant", "food", "dining"})) or "foodie" in style_tags


def _has_restaurant_anchor(items: list[dict[str, Any]]) -> bool:
    for item in items:
        place = item.get("place") or {}
        category = str(place.get("category") or "").lower()
        if category in {"restaurant", "bistro", "brasserie"}:
            return True
        if _role_key(item) == "restaurant" and category not in {"cafe", "bakery"}:
            return True
    return False


def _fallback_french_dinner_item(anchor: dict[str, float], language: str) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "time_slot": "evening",
        "start_time": "18:35",
        "title": _copy(language, "Local bistro dinner", "로컬 비스트로 저녁"),
        "place": {
            "name": _copy(language, "Local Paris Bistro", "로컬 파리 비스트로"),
            "category": "restaurant",
            "cuisine": ["french", "bistro"],
            "coordinates": dict(anchor),
        },
        "description": _copy(
            language,
            "A French bistro-style dinner anchor added to satisfy the requested local evening mood.",
            "요청한 로컬 비스트로 분위기를 맞추기 위해 넣은 프렌치 저녁 식사 앵커입니다.",
        ),
        "estimated_duration": _copy(language, "1 hour 30 minutes", "1시간 30분"),
    }


def _prefers_french_dinner(preference_profile: dict[str, Any]) -> bool:
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    meal_preferences = {str(value).lower() for value in (brief or {}).get("meal_preference") or []}
    style_tags = {str(value).lower() for value in preference_profile.get("style_tags") or []} if isinstance(preference_profile, dict) else set()
    return bool(meal_preferences.intersection({"french", "bistro", "brasserie", "romantic"})) or "french" in style_tags


def _has_evening_meal(items: list[dict[str, Any]]) -> bool:
    for item in items:
        if str(item.get("time_slot") or "") != "evening":
            continue
        place = item.get("place") or {}
        category = str(place.get("category") or "").lower()
        if category in MEAL_PLACE_CATEGORIES or _is_dinner_item(item):
            return True
    return False


_FINAL_ANCHOR_ALIASES: dict[str, tuple[str, ...]] = {
    "eiffel": ("eiffel", "eiffeltower", "toureiffel", "\uc5d0\ud3a0", "\uc5d0\ud3a0\ud0d1"),
    "arc": ("arc", "arcdetriomphe", "triomphe", "\uac1c\uc120\ubb38"),
    "seine": ("seine", "seineriver", "\uc13c\uac15"),
    "jazz": ("jazz", "jazzbar", "caveaudelahuchette", "huchette", "\uc7ac\uc988", "\uc7ac\uc988\ubc14", "\uc704\uc158\ud2b8"),
    "montmartre": ("montmartre", "sacrecoeur", "\ubabd\ub9c8\ub974\ud2b8\ub974", "\ubabd\ub9c8\ub974\ud2b8", "\uc0ac\ud06c\ub808\ucf8c\ub974"),
}
_FINAL_ANCHOR_CUES = ("finish", "final", "end", "\ub9c8\ubb34\ub9ac", "\ub9c8\uc9c0\ub9c9", "\ub05d")
_FINAL_ANCHOR_AVOID_CUES = ("avoid", "skip", "exclude", "without", "\ub9d0\uace0", "\ube7c", "\uc81c\uc678", "\uac00\uc9c0\ub9c8")
_FINAL_ANCHOR_NIGHT_CUES = ("night", "nightview", "night_view", "sparkling", "\uc57c\uacbd", "\ubc24", "\uc57c\uac04", "\uc11d\uc591", "\uc120\uc14b", "sunset")
_SCOPED_DAYPART_ALIASES: dict[str, tuple[str, ...]] = {
    "louvre": ("louvre", "louvremuseum", "\ub8e8\ube0c\ub974"),
    "orsay": ("orsay", "museedorsay", "dorsay", "\uc624\ub974\uc138"),
    "notre": ("notredame", "notredamecathedral", "\ub178\ud2b8\ub974\ub2f4"),
    "sainte": ("saintechapelle", "saintechapelle", "saintchapelle", "chapelle", "\uc0dd\ud2b8\uc0e4\ud3a0"),
    "marais": ("marais", "lemarais", "\ub9c8\ub808"),
    "montmartre": _FINAL_ANCHOR_ALIASES["montmartre"],
    "eiffel": _FINAL_ANCHOR_ALIASES["eiffel"],
    "arc": _FINAL_ANCHOR_ALIASES["arc"],
    "champs": ("champselysees", "avenuedeschampselysees", "\uc0f9\uc824\ub9ac\uc81c", "\uc0f9\uc824\ub9ac\uc81c\uac70\ub9ac"),
    "seine": _FINAL_ANCHOR_ALIASES["seine"],
    "garnier": ("palaisgarnier", "operagarnier", "opera", "garnier", "\uc624\ud398\ub77c", "\uac00\ub974\ub2c8\uc5d0"),
    "palais_royal": ("palaisroyal", "\ud314\ub808\ub8e8\uc544\uc584"),
    "jazz": _FINAL_ANCHOR_ALIASES["jazz"],
}
_MORNING_CUES = ("morning", "breakfast", "\uc624\uc804", "\uc544\uce68")
_AFTERNOON_CUES = ("afternoon", "\uc624\ud6c4", "\ub0ae", "\ub2a6\uc740\uc624\ud6c4")
_STRUCTURED_SLOT_MINUTES = {
    "morning": 9 * 60 + 15,
    "lunch": 12 * 60 + 30,
    "afternoon": 13 * 60 + 30,
    "evening": 18 * 60 + 15,
    "night": 20 * 60 + 30,
}


def _move_final_anchor_to_end(items: list[dict[str, Any]], preference_profile: dict[str, Any]) -> list[dict[str, Any]]:
    if len(items) < 2:
        return items
    anchor_kind = _requested_final_anchor_kind(preference_profile)
    if not anchor_kind:
        return items

    items = _drop_unrequested_night_view_fillers(items, anchor_kind, preference_profile)
    items = _apply_scoped_daypart_times(items, preference_profile)
    anchor_index = next((index for index, item in enumerate(items) if _is_final_anchor_item(item, anchor_kind)), None)
    if anchor_index is None:
        return items

    final_item = dict(items[anchor_index])
    final_item["time_slot"] = "evening"
    final_item["start_time"] = _final_anchor_start_time(anchor_kind, preference_profile, final_item)
    final_item["isNightViewSpot"] = True
    original_lock_reason = str(final_item.get("slotLockReason") or "").strip()
    if original_lock_reason and original_lock_reason != "final_night_anchor":
        final_item["slotLockLabel"] = original_lock_reason
    final_item["slotLockReason"] = "final_night_anchor"
    final_item["finalAnchor"] = True
    final_item["finalAnchorKind"] = anchor_kind

    reordered = [*items[:anchor_index], *items[anchor_index + 1 :], final_item]
    reordered = _rebalance_museum_day_before_final_anchor(reordered, preference_profile)
    return _tighten_evening_anchors_before_final(reordered)


def _drop_unrequested_night_view_fillers(
    items: list[dict[str, Any]],
    final_anchor_kind: str,
    preference_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    requested_text = _compact_source_text(" ".join(str(value) for value in (brief or {}).get("must_include") or []))
    filtered: list[dict[str, Any]] = []
    for item in items:
        item_anchor_kind = _anchor_kind_for_item(item)
        if item_anchor_kind == final_anchor_kind:
            filtered.append(item)
            continue
        if item_anchor_kind and _is_optional_night_view_filler(item) and not _anchor_kind_requested(item_anchor_kind, requested_text):
            continue
        if _is_optional_evening_filler(item) and not _is_marked_must_include(item):
            continue
        filtered.append(item)
    return filtered


def _anchor_kind_for_item(item: dict[str, Any]) -> str | None:
    for kind in _FINAL_ANCHOR_ALIASES:
        if _is_final_anchor_item(item, kind):
            return kind
    return None


def _anchor_kind_requested(anchor_kind: str, requested_text: str) -> bool:
    return any(_compact_source_text(alias) in requested_text for alias in _FINAL_ANCHOR_ALIASES.get(anchor_kind, ()))


def _is_optional_night_view_filler(item: dict[str, Any]) -> bool:
    if _role_key(item) == "night_view":
        return True
    return bool(item.get("isNightViewSpot") or item.get("slotLockReason"))


def _is_optional_evening_filler(item: dict[str, Any]) -> bool:
    if _role_key(item) in {"restaurant", "cafe", "meal_placeholder", "museum", "cathedral"}:
        return False
    if str(item.get("time_slot") or "") != "evening" and (_parse_clock_minutes(item.get("start_time")) or 0) < EVENING_START_MINUTES:
        return False
    place = item.get("place") or {}
    category = str(place.get("category") or "").lower()
    return category in {"landmark", "neighborhood", "park", "garden"}


def _is_marked_must_include(item: dict[str, Any]) -> bool:
    slot_tags = item.get("slotTags") or item.get("slot_tags") or []
    if not isinstance(slot_tags, list):
        slot_tags = [slot_tags]
    return any(str(tag).lower() == "must_include" for tag in slot_tags)


def _rebalance_museum_day_before_final_anchor(items: list[dict[str, Any]], preference_profile: dict[str, Any]) -> list[dict[str, Any]]:
    if len(items) < 4:
        return items
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    meal_preferences = {str(value).lower() for value in (brief or {}).get("meal_preference") or []}
    if meal_preferences.intersection({"brunch", "breakfast"}):
        return items

    final_item = items[-1]
    pre_final = list(items[:-1])
    museums = [item for item in pre_final if _role_key(item) == "museum"]
    if len(museums) < 2:
        return items

    museum_ids = {id(item) for item in museums}
    lunches = [item for item in pre_final if id(item) not in museum_ids and _is_lunch_item(item)]
    dinners = [
        item
        for item in pre_final
        if id(item) not in museum_ids
        and id(item) not in {id(lunch) for lunch in lunches}
        and _role_key(item) == "restaurant"
        and not _is_lunch_item(item)
    ]
    others = [
        item
        for item in pre_final
        if id(item) not in museum_ids
        and id(item) not in {id(lunch) for lunch in lunches}
        and id(item) not in {id(dinner) for dinner in dinners}
    ]

    ordered: list[dict[str, Any]] = []
    first_museum = dict(museums[0])
    first_museum["time_slot"] = "morning"
    first_museum["start_time"] = "09:45"
    ordered.append(first_museum)
    if lunches:
        lunch = dict(lunches[0])
        lunch["time_slot"] = "lunch"
        lunch["start_time"] = "12:35"
        ordered.append(lunch)
    for offset, museum in enumerate(museums[1:], start=0):
        museum_item = dict(museum)
        museum_item["time_slot"] = "afternoon"
        museum_item["start_time"] = _format_clock(14 * 60 + offset * 100)
        ordered.append(museum_item)
    ordered.extend(others)
    for dinner in dinners:
        dinner_item = dict(dinner)
        dinner_item["time_slot"] = "evening"
        dinner_item["start_time"] = "18:30"
        ordered.append(dinner_item)
    ordered.append(final_item)
    return ordered


def _requested_final_anchor_kind(preference_profile: dict[str, Any]) -> str | None:
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    explicit_final = str((brief or {}).get("final_anchor") or "").strip()
    explicit_canonical = _canonical_from_target_text(explicit_final)
    if explicit_canonical in _FINAL_ANCHOR_ALIASES:
        return explicit_canonical
    source_text = str((brief or {}).get("source_text") or "")
    compact = _compact_source_text(source_text)
    if not compact:
        return None

    scored: list[tuple[int, str]] = []
    for kind, aliases in _FINAL_ANCHOR_ALIASES.items():
        score = _scoped_cue_distance(compact, aliases, _FINAL_ANCHOR_CUES)
        if score is not None:
            scored.append((score, kind))
    if not scored:
        for kind, aliases in _FINAL_ANCHOR_ALIASES.items():
            score = _scoped_cue_distance(compact, aliases, _FINAL_ANCHOR_NIGHT_CUES)
            if score is not None:
                scored.append((score + 100, kind))
    if not scored:
        return None
    scored.sort()
    return scored[0][1]


def _final_anchor_start_time(anchor_kind: str, preference_profile: dict[str, Any], item: dict[str, Any]) -> str:
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    source_text = str((brief or {}).get("source_text") or "")
    aliases = _FINAL_ANCHOR_ALIASES.get(anchor_kind, ())
    if anchor_kind == "jazz":
        return "21:15"
    if _scoped_cue_distance(_compact_source_text(source_text), aliases, ("night", "nightview", "\uc57c\uacbd", "\ubc24", "\uc57c\uac04")) is not None:
        return "20:15"
    preferred = _parse_clock_minutes(item.get("start_time"))
    if preferred is not None and EVENING_START_MINUTES <= preferred < 20 * 60:
        return _format_clock(preferred)
    return "18:50"


def _compact_source_text(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\uac00-\ud7a3]+", "", str(value or "")).lower()


def _scoped_cue_distance(
    compact_text: str,
    aliases: tuple[str, ...],
    cues: tuple[str, ...],
    *,
    before: int = 6,
    after: int = 30,
    respect_avoid: bool = True,
) -> int | None:
    alias_values = [_compact_source_text(alias) for alias in aliases if _compact_source_text(alias)]
    cue_values = [_compact_source_text(cue) for cue in cues if _compact_source_text(cue)]
    avoid_values = [_compact_source_text(cue) for cue in _FINAL_ANCHOR_AVOID_CUES if _compact_source_text(cue)]
    best: int | None = None
    for alias in alias_values:
        start = compact_text.find(alias)
        while start >= 0:
            avoid_after_window = compact_text[start + len(alias) : start + len(alias) + 10]
            avoid_before_window = compact_text[max(0, start - 12) : start]
            avoid_after = any(cue in avoid_after_window for cue in avoid_values)
            english_avoid_before = any(cue in avoid_before_window for cue in ("avoid", "without", "skip", "exclude"))
            if not respect_avoid or not (avoid_after or english_avoid_before):
                window_start = max(0, start - before)
                window = compact_text[window_start : start + len(alias) + after]
                for cue in cue_values:
                    cue_index = window.find(cue)
                    if cue_index >= 0:
                        absolute_cue_index = window_start + cue_index
                        distance = abs(absolute_cue_index - start)
                        best = distance if best is None else min(best, distance)
            start = compact_text.find(alias, start + len(alias))
    return best


def _is_final_anchor_item(item: dict[str, Any], anchor_kind: str) -> bool:
    return _item_matches_aliases(item, _FINAL_ANCHOR_ALIASES.get(anchor_kind, ()))


def _item_matches_aliases(item: dict[str, Any], aliases: tuple[str, ...]) -> bool:
    place = item.get("place") or {}
    text = _compact_source_text(
        " ".join(
            [
                str(item.get("title") or ""),
                str(place.get("name") or ""),
                str(place.get("slug") or place.get("place_id") or ""),
            ]
        )
    )
    alias_values = [_compact_source_text(token) for token in aliases if _compact_source_text(token)]
    for alias in alias_values:
        if alias == "arc" and "arcdetriomphe" not in text:
            continue
        if alias == "opera" and "garnier" not in text and "palaisgarnier" not in text:
            continue
        if alias in text:
            return True
    return False


def _apply_scoped_daypart_times(items: list[dict[str, Any]], preference_profile: dict[str, Any]) -> list[dict[str, Any]]:
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    compact = _compact_source_text(str((brief or {}).get("source_text") or ""))
    if not compact:
        return items

    morning_offset = 0
    afternoon_offset = 0
    adjusted: list[dict[str, Any]] = []
    changed = False
    for item in items:
        next_item = item
        for aliases in _SCOPED_DAYPART_ALIASES.values():
            if not _item_matches_aliases(item, aliases):
                continue
            morning_after_score = _scoped_cue_after_alias(compact, aliases, _MORNING_CUES, after=12)
            afternoon_after_score = _scoped_cue_after_alias(compact, aliases, _AFTERNOON_CUES, after=12)
            morning_score = _scoped_cue_distance(compact, aliases, _MORNING_CUES, before=16, after=16, respect_avoid=False)
            afternoon_score = _scoped_cue_distance(compact, aliases, _AFTERNOON_CUES, before=16, after=16, respect_avoid=False)
            if afternoon_after_score is not None and (morning_after_score is None or afternoon_after_score <= morning_after_score):
                next_item = dict(item)
                next_item["time_slot"] = "afternoon"
                next_item["start_time"] = _format_clock((13 * 60 + 30) + afternoon_offset * 85)
                next_item["slotLockReason"] = next_item.get("slotLockReason") or "scoped_daypart"
                afternoon_offset += 1
                changed = True
                break
            if morning_after_score is not None:
                next_item = dict(item)
                next_item["time_slot"] = "morning"
                next_item["start_time"] = _format_clock(9 * 60 + 15 + morning_offset * 85)
                next_item["slotLockReason"] = next_item.get("slotLockReason") or "scoped_daypart"
                morning_offset += 1
                changed = True
                break
            if morning_score is not None and (afternoon_score is None or morning_score <= afternoon_score):
                next_item = dict(item)
                next_item["time_slot"] = "morning"
                next_item["start_time"] = _format_clock(9 * 60 + 15 + morning_offset * 85)
                next_item["slotLockReason"] = next_item.get("slotLockReason") or "scoped_daypart"
                morning_offset += 1
                changed = True
                break
            if afternoon_score is not None:
                next_item = dict(item)
                next_item["time_slot"] = "afternoon"
                next_item["start_time"] = _format_clock((13 * 60 + 30) + afternoon_offset * 85)
                next_item["slotLockReason"] = next_item.get("slotLockReason") or "scoped_daypart"
                afternoon_offset += 1
                changed = True
                break
        adjusted.append(next_item)
    if not changed:
        return items
    return sorted(
        adjusted,
        key=lambda item: (
            _parse_clock_minutes(item.get("start_time")) is None,
            _parse_clock_minutes(item.get("start_time")) or 0,
            0 if item.get("slotLockReason") == "scoped_daypart" else 1,
        ),
    )


def _apply_structured_place_constraints(items: list[dict[str, Any]], preference_profile: dict[str, Any]) -> list[dict[str, Any]]:
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    if not isinstance(brief, dict):
        return items
    constraints = [constraint for constraint in brief.get("place_constraints") or [] if isinstance(constraint, dict)]
    ordered_anchors = [str(value) for value in brief.get("ordered_anchors") or [] if str(value).strip()]
    final_anchor = str(brief.get("final_anchor") or "").strip()
    if not constraints and not ordered_anchors and not final_anchor:
        return items

    slot_offsets = {"morning": 0, "lunch": 0, "afternoon": 0, "evening": 0, "night": 0}
    adjusted: list[dict[str, Any]] = []
    changed = False
    for item in items:
        next_item = dict(item)
        constraint = next(
            (
                constraint
                for constraint in constraints
                if str(constraint.get("intent") or "") != "avoid"
                and _item_matches_constraint(next_item, constraint)
            ),
            None,
        )
        if constraint:
            slot = str(constraint.get("time_slot") or "").strip()
            if slot in _STRUCTURED_SLOT_MINUTES:
                normalized_slot = "evening" if slot == "night" else slot
                minutes = _STRUCTURED_SLOT_MINUTES[slot] + slot_offsets[slot] * 85
                slot_offsets[slot] += 1
                next_item["time_slot"] = normalized_slot
                next_item["start_time"] = _format_clock(minutes)
                next_item["slotLockReason"] = "structured_place_constraint"
                changed = True
            if constraint.get("final") or (final_anchor and _item_matches_constraint(next_item, {"target": final_anchor})):
                next_item["finalAnchor"] = True
                next_item["finalAnchorKind"] = str(constraint.get("canonical") or final_anchor or constraint.get("target") or "")
                next_item["time_slot"] = "evening"
                next_item["start_time"] = _format_clock(max(_parse_clock_minutes(next_item.get("start_time")) or 0, 20 * 60 + 15))
                next_item["slotLockReason"] = "structured_final_anchor"
                changed = True
        adjusted.append(next_item)

    if ordered_anchors:
        adjusted = _reorder_structured_anchors(adjusted, ordered_anchors)
        changed = True
    if not changed:
        return items
    return sorted(
        adjusted,
        key=lambda item: (
            _parse_clock_minutes(item.get("start_time")) is None,
            _parse_clock_minutes(item.get("start_time")) or 0,
            0 if item.get("slotLockReason") else 1,
        ),
    )


def _item_matches_constraint(item: dict[str, Any], constraint: dict[str, Any]) -> bool:
    canonical = str(constraint.get("canonical") or "").strip()
    target = str(constraint.get("target") or "").strip()
    aliases: list[str] = []
    if canonical in _SCOPED_DAYPART_ALIASES:
        aliases.extend(_SCOPED_DAYPART_ALIASES[canonical])
    if target:
        aliases.append(target)
    return bool(aliases) and _item_matches_aliases(item, tuple(aliases))


def _reorder_structured_anchors(items: list[dict[str, Any]], ordered_anchors: list[str]) -> list[dict[str, Any]]:
    if len(ordered_anchors) < 2:
        return items
    remaining = list(items)
    ordered_items: list[dict[str, Any]] = []
    for anchor in ordered_anchors:
        index = next((idx for idx, item in enumerate(remaining) if _item_matches_constraint(item, {"target": anchor})), None)
        if index is None:
            continue
        ordered_items.append(remaining.pop(index))
    if len(ordered_items) < 2:
        return items
    first_anchor_position = min(
        (idx for idx, item in enumerate(items) if any(item is anchor_item or _item_keyish(item) == _item_keyish(anchor_item) for anchor_item in ordered_items)),
        default=0,
    )
    return [*remaining[:first_anchor_position], *ordered_items, *remaining[first_anchor_position:]]


def _item_keyish(item: dict[str, Any]) -> str:
    place = item.get("place") or {}
    return _compact_source_text(" ".join(str(value or "") for value in (place.get("slug"), place.get("place_id"), place.get("name"), item.get("title"))))


def _scoped_cue_after_alias(
    compact_text: str,
    aliases: tuple[str, ...],
    cues: tuple[str, ...],
    *,
    after: int,
) -> int | None:
    alias_values = [_compact_source_text(alias) for alias in aliases if _compact_source_text(alias)]
    cue_values = [_compact_source_text(cue) for cue in cues if _compact_source_text(cue)]
    best: int | None = None
    for alias in alias_values:
        start = compact_text.find(alias)
        while start >= 0:
            after_text = compact_text[start + len(alias) : start + len(alias) + after]
            next_alias_offset = _next_scoped_daypart_alias_offset(after_text)
            if next_alias_offset >= 0:
                after_text = after_text[:next_alias_offset]
            for cue in cue_values:
                cue_index = after_text.find(cue)
                if cue_index >= 0:
                    before_cue = after_text[:cue_index]
                    if not any(marker in before_cue for marker in ("는", "은", "엔", "에는", "에서", "를", "을")):
                        continue
                    if cue_index > 5 or any(token in before_cue for token in ("보고", "이후", "다음", "후에", "뒤")):
                        continue
                    best = cue_index if best is None else min(best, cue_index)
            start = compact_text.find(alias, start + len(alias))
    return best


def _next_scoped_daypart_alias_offset(text: str) -> int:
    offsets = [
        text.find(alias_value)
        for aliases in _SCOPED_DAYPART_ALIASES.values()
        for alias in aliases
        if (alias_value := _compact_source_text(alias)) and alias_value in text
    ]
    return min(offsets) if offsets else -1


_ORDER_SIGNAL_CUES = ("순서", "그다음", "그다음에", "다음", "이후", "후", "뒤", "after", "then")
_ORDER_TOKEN_ALIASES: dict[str, tuple[str, ...]] = {
    "brunch": ("brunch", "\ube0c\ub7f0\uce58"),
    "cafe": ("cafe", "coffee", "\uce74\ud398"),
    "louvre": _SCOPED_DAYPART_ALIASES["louvre"],
    "orsay": _SCOPED_DAYPART_ALIASES["orsay"],
    "notre": _SCOPED_DAYPART_ALIASES["notre"],
    "sainte": _SCOPED_DAYPART_ALIASES["sainte"],
    "marais": _SCOPED_DAYPART_ALIASES["marais"],
    "montmartre": _SCOPED_DAYPART_ALIASES["montmartre"],
    "tuileries": ("tuileries", "\ud280\ub974\ub9ac"),
    "luxembourg": ("luxembourg", "뤽상부르", "룩셈부르크"),
    "seine": _SCOPED_DAYPART_ALIASES["seine"],
    "eiffel": _SCOPED_DAYPART_ALIASES["eiffel"],
    "arc": _SCOPED_DAYPART_ALIASES["arc"],
    "garnier": _SCOPED_DAYPART_ALIASES["garnier"],
    "palais_royal": _SCOPED_DAYPART_ALIASES["palais_royal"],
    "jazz": _SCOPED_DAYPART_ALIASES["jazz"],
    "dinner": ("dinner", "\ub514\ub108", "\uc800\ub141"),
}


def _apply_explicit_source_order(
    items: list[dict[str, Any]],
    preference_profile: dict[str, Any],
    *,
    keep_final: bool = False,
) -> list[dict[str, Any]]:
    if len(items) < 2:
        return items
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    compact = _compact_source_text(str((brief or {}).get("source_text") or ""))
    if not compact or not any(_compact_source_text(cue) in compact for cue in _ORDER_SIGNAL_CUES):
        return items

    tail: list[dict[str, Any]] = []
    working = list(items)
    if keep_final and working and _is_locked_final_anchor(working[-1]):
        tail = [working.pop()]

    positioned: list[tuple[int, int, dict[str, Any]]] = []
    unpositioned: list[tuple[int, dict[str, Any]]] = []
    for index, item in enumerate(working):
        position = _source_order_position(item, compact)
        if position is None:
            unpositioned.append((index, item))
        else:
            positioned.append((position, index, item))
    if len(positioned) < 2:
        return items

    positioned.sort(key=lambda value: (value[0], value[1]))
    ordered_positioned = [item for _, _, item in positioned]
    named_indices = {index for _, index, _ in positioned}
    merged: list[dict[str, Any]] = []
    inserted = False
    for index, item in enumerate(working):
        if index in named_indices:
            if not inserted:
                merged.extend(ordered_positioned)
                inserted = True
            continue
        merged.append(item)
    if not inserted:
        merged.extend(ordered_positioned)
    return [*merged, *tail]


def _is_locked_final_anchor(item: dict[str, Any]) -> bool:
    return bool(item.get("finalAnchor")) or str(item.get("slotLockReason") or "") == "final_night_anchor"


def _source_order_position(item: dict[str, Any], compact_source: str) -> int | None:
    candidates: list[int] = []
    for key, aliases in _ORDER_TOKEN_ALIASES.items():
        if key == "brunch" and not _is_brunch_item(item):
            continue
        if key == "cafe" and _role_key(item) != "cafe":
            continue
        if key == "dinner" and not _is_dinner_item(item):
            continue
        if key not in {"brunch", "cafe", "dinner"} and not _item_matches_aliases(item, aliases):
            continue
        alias_positions = [
            compact_source.find(alias_value)
            for alias in aliases
            if (alias_value := _compact_source_text(alias)) and compact_source.find(alias_value) >= 0
        ]
        if alias_positions:
            candidates.append(min(alias_positions))
    return min(candidates) if candidates else None


_NEGATIVE_NIGHT_CUES = (
    "\uc57c\uacbd\uc740\uc5c6\uc5b4\ub3c4",
    "\uc57c\uacbd\uc5c6\uc5b4\ub3c4",
    "\uc57c\uacbd\uc740\ube7c",
    "\uc57c\uacbd\ube7c",
    "\uc57c\uacbd\uae4c\uc9c0\ubb34\ub9ac\ud558\uc9c0",
    "\ubc24\ub2a6\uac8c\uae4c\uc9c0\ubb34\ub9ac",
    "\ubc24\ub2a6\uc9c0\uc54a\uac8c",
    "\uc774\ub978\ub9c8\ubb34\ub9ac",
    "야경은없어도",
    "야경없어도",
    "야경은없",
    "야경없",
    "야경은빼",
    "야경빼",
    "야경말고",
    "야경대신",
    "밤일정은빼",
    "밤일정빼",
    "밤늦게까지는싫",
    "밤늦게까지싫",
)


def _drop_negative_night_tail_items(items: list[dict[str, Any]], preference_profile: dict[str, Any]) -> list[dict[str, Any]]:
    if len(items) < 2:
        return items
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    compact = _compact_source_text(str((brief or {}).get("source_text") or ""))
    if not compact or not any(_compact_source_text(cue) in compact for cue in _NEGATIVE_NIGHT_CUES):
        return items
    required_text = _compact_source_text(" ".join(str(value) for value in (brief or {}).get("must_include") or []))
    trimmed = list(items)
    while len(trimmed) > 1:
        last = trimmed[-1]
        preferred = _parse_clock_minutes(last.get("start_time"))
        if preferred is not None and preferred < 20 * 60:
            break
        if _is_marked_must_include(last) or _item_requested_by_brief(last, required_text):
            break
        trimmed.pop()
    return trimmed


def _item_requested_by_brief(item: dict[str, Any], compact_required_text: str) -> bool:
    if not compact_required_text:
        return False
    for aliases in [*_FINAL_ANCHOR_ALIASES.values(), *_SCOPED_DAYPART_ALIASES.values()]:
        if _item_matches_aliases(item, aliases) and any(_compact_source_text(alias) in compact_required_text for alias in aliases):
            return True
    place = item.get("place") or {}
    item_text = _compact_source_text(
        " ".join(
            [
                str(item.get("title") or ""),
                str(place.get("name") or ""),
                str(place.get("slug") or place.get("place_id") or ""),
            ]
        )
    )
    return bool(item_text and item_text in compact_required_text)


def _tighten_evening_anchors_before_final(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(items) < 2:
        return items
    tightened: list[dict[str, Any]] = []
    next_anchor_minutes = 18 * 60 + 50
    for item in items[:-1]:
        if not _should_pull_evening_anchor_forward(item):
            tightened.append(item)
            continue
        anchor_item = dict(item)
        anchor_item["time_slot"] = "evening"
        anchor_item["start_time"] = _format_clock(next_anchor_minutes)
        anchor_item["isNightViewSpot"] = True
        tightened.append(anchor_item)
        next_anchor_minutes += 75
    tightened.append(items[-1])
    return tightened


def _should_pull_evening_anchor_forward(item: dict[str, Any]) -> bool:
    role = _role_key(item)
    if role not in {"night_view", "landmark"} and not item.get("isNightViewSpot") and not item.get("slotLockReason"):
        return False
    start_minutes = _parse_clock_minutes(item.get("start_time"))
    if start_minutes is None or start_minutes < 20 * 60:
        return False
    place = item.get("place") or {}
    category = str(place.get("category") or "").lower()
    if category in MEAL_PLACE_CATEGORIES:
        return False
    text = _compact_source_text(
        " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("description") or ""),
                str(place.get("name") or ""),
                str(place.get("slug") or place.get("place_id") or ""),
            ]
        )
    )
    return any(token in text for token in ("night", "view", "\uc57c\uacbd", "seine", "\uc13c\uac15", "eiffel", "\uc5d0\ud3a0", "arc", "\uac1c\uc120\ubb38"))


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
    current_minutes = _initial_day_start_minutes(items, pace_level, preference_profile)
    for index, item in enumerate(items):
        item = dict(item)
        role = _role_key(item)
        next_item = items[index + 1] if index + 1 < len(items) else None
        next_role = _role_key(next_item) if isinstance(next_item, dict) else ""
        next_name = str((next_item or {}).get("place", {}).get("name") or (next_item or {}).get("title") or "").strip()
        preferred_start = _preferred_start_minutes(item, role)
        if preferred_start is not None and preferred_start > current_minutes:
            wait_minutes = preferred_start - current_minutes
            compact_pace = pace_level != "slow"
            time_anchor = _is_time_anchor_item(item, role)
            scoped_daypart_anchor = str(item.get("slotLockReason") or "") == "scoped_daypart"
            gap_threshold = 360 if time_anchor else 240 if scoped_daypart_anchor else 45 if compact_pace else GAP_DISCLOSURE_MINUTES
            can_pull_forward = (wait_minutes >= 60 or (compact_pace and wait_minutes >= 20)) and not time_anchor and not item.get("slotLockReason")
            if can_pull_forward:
                preferred_start = current_minutes
                wait_minutes = 0
            if wait_minutes >= gap_threshold:
                scheduled_items.append(_gap_item(item, current_minutes, preferred_start, preference_profile, language))
            current_minutes = preferred_start

        duration = _stay_duration_minutes(
            item,
            role,
            pace_level,
            low_walking=bool(preference_profile.get("low_walking")),
        )
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
        item["isNightViewSpot"] = (
            bool(item.get("isNightViewSpot"))
            or role == "night_view"
            or _is_night_view_lock(item)
            or (_is_late_bar_item(item) and start_minutes >= EVENING_START_MINUTES)
        )
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
    scheduled_items = _apply_scheduled_pair_daypart_locks(scheduled_items, preference_profile)
    scheduled_items = _trim_scheduled_negative_night_tail(scheduled_items, preference_profile)
    scheduled_items = _trim_scheduled_day_overflow(scheduled_items, language)
    items[:] = scheduled_items
    return items


def _trim_scheduled_day_overflow(
    scheduled_items: list[dict[str, Any]],
    language: str,
) -> list[dict[str, Any]]:
    """Keep generated day schedules inside a human-readable same-day window."""

    if not scheduled_items:
        return scheduled_items

    bounded: list[dict[str, Any]] = []
    for item in scheduled_items:
        start_minutes = _parse_clock_minutes(item.get("start_time"))
        end_minutes = _parse_clock_minutes(item.get("end_time"))
        if start_minutes is None:
            bounded.append(item)
            continue
        if start_minutes >= DAY_END_MINUTES:
            continue
        next_item = dict(item)
        if end_minutes is not None and end_minutes > DAY_END_MINUTES:
            end_minutes = DAY_END_MINUTES
            duration = max(15, end_minutes - start_minutes)
            next_item["end_time"] = _format_clock(end_minutes)
            next_item["duration_minutes"] = duration
            next_item["estimated_duration"] = _format_duration_minutes(duration, language)
        if start_minutes > LATEST_STOP_START_MINUTES and next_item.get("itemKind") != "gap":
            next_item["time_slot"] = "evening"
            next_item["start_time"] = _format_clock(LATEST_STOP_START_MINUTES)
            duration = int(next_item.get("duration_minutes") or 45)
            next_item["end_time"] = _format_clock(min(DAY_END_MINUTES, LATEST_STOP_START_MINUTES + duration))
        bounded.append(next_item)

    while bounded and bounded[-1].get("itemKind") == "gap":
        bounded.pop()
    return bounded or scheduled_items[:1]


def _apply_scheduled_pair_daypart_locks(
    scheduled_items: list[dict[str, Any]],
    preference_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    if len(scheduled_items) < 2:
        return scheduled_items
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    compact = _compact_source_text(str((brief or {}).get("source_text") or ""))
    cathedral_pair_morning = (
        ("notredame" in compact or "노트르담" in compact)
        and ("saintechapelle" in compact or "생트샤펠" in compact or "생트샤펠" in compact)
        and any(cue in compact for cue in ("아침", "오전", "morning"))
    )
    if not cathedral_pair_morning:
        return scheduled_items

    adjusted: list[dict[str, Any]] = []
    morning_index = 0
    for item in scheduled_items:
        if item.get("itemKind") != "gap" and (
            _item_matches_aliases(item, _SCOPED_DAYPART_ALIASES["notre"])
            or _item_matches_aliases(item, _SCOPED_DAYPART_ALIASES["sainte"])
        ):
            next_item = dict(item)
            start_minutes = 9 * 60 + 15 + morning_index * 85
            duration = int(next_item.get("duration_minutes") or _stay_duration_minutes(next_item, _role_key(next_item), "normal"))
            next_item["time_slot"] = "morning"
            next_item["start_time"] = _format_clock(start_minutes)
            next_item["end_time"] = _format_clock(start_minutes + duration)
            next_item["slotLockReason"] = next_item.get("slotLockReason") or "scoped_daypart"
            morning_index += 1
            adjusted.append(next_item)
            continue
        adjusted.append(item)
    if morning_index < 2:
        return scheduled_items
    return sorted(adjusted, key=lambda item: (_parse_clock_minutes(item.get("start_time")) is None, _parse_clock_minutes(item.get("start_time")) or 0))


def _trim_scheduled_negative_night_tail(
    scheduled_items: list[dict[str, Any]],
    preference_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    if len(scheduled_items) < 2:
        return scheduled_items
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile, dict) else {}
    compact = _compact_source_text(str((brief or {}).get("source_text") or ""))
    if not compact or not any(_compact_source_text(cue) in compact for cue in _NEGATIVE_NIGHT_CUES):
        return scheduled_items
    required_text = _compact_source_text(" ".join(str(value) for value in (brief or {}).get("must_include") or []))
    trimmed = list(scheduled_items)
    while len(trimmed) > 1:
        last = trimmed[-1]
        if last.get("itemKind") == "gap":
            trimmed.pop()
            continue
        start_minutes = _parse_clock_minutes(last.get("start_time"))
        if start_minutes is None or start_minutes < 20 * 60 + 30:
            break
        if _is_marked_must_include(last) or _item_requested_by_brief(last, required_text):
            break
        trimmed.pop()
    return trimmed


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
    if any(token in haystack for token in ("cafe", "coffee", "bakery", "카페")):
        return "cafe"
    if _is_meal_item(item):
        return "restaurant"
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


def _is_walk_like_item(item: dict[str, Any], role: str | None = None) -> bool:
    role = role or _role_key(item)
    if role in {"park", "garden", "neighborhood"}:
        return True
    place = item.get("place") or {}
    text = _compact_source_text(
        " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("description") or ""),
                str(place.get("name") or ""),
                str(place.get("category") or ""),
                " ".join(str(tag) for tag in place.get("tags") or []),
            ]
        )
    )
    return any(
        token in text
        for token in (
            "walk",
            "walking",
            "stroll",
            "promenade",
            "seine",
            "river",
            "\uc0b0\ucc45",
            "\uac77\uae30",
            "\uac78\uc5b4",
            "\uc138\ub098",
            "\uc13c\uac15",
        )
    )


def _is_lunch_item(item: dict[str, Any]) -> bool:
    place = item.get("place") or {}
    category = str(place.get("category") or "").lower()
    title_text = f"{item.get('title') or ''} {item.get('description') or ''}".lower()
    if "lunch" in title_text or "점심" in title_text:
        return True
    return str(item.get("time_slot") or "") == "lunch" and category in MEAL_PLACE_CATEGORIES


def _is_brunch_item(item: dict[str, Any]) -> bool:
    place = item.get("place") or {}
    cuisine = place.get("cuisine") or []
    if not isinstance(cuisine, list):
        cuisine = [cuisine]
    slot_tags = item.get("slotTags") or item.get("slot_tags") or []
    if not isinstance(slot_tags, list):
        slot_tags = [slot_tags]
    text = " ".join(
        [
            str(item.get("time_slot") or ""),
            str(item.get("title") or ""),
            str(item.get("description") or ""),
            " ".join(str(value) for value in cuisine if value),
            " ".join(str(value) for value in slot_tags if value),
        ]
    ).lower()
    return any(token in text for token in ("brunch", "breakfast", "bakery", "coffee"))


def _is_time_anchor_item(item: dict[str, Any], role: str) -> bool:
    if _is_locked_final_anchor(item):
        return True
    if role in {"night_view", "meal_placeholder", "restaurant"}:
        return True
    place = item.get("place") or {}
    category = str(place.get("category") or "").lower()
    slot_tags = item.get("slotTags") or item.get("slot_tags") or []
    if not isinstance(slot_tags, list):
        slot_tags = [slot_tags]
    tag_text = " ".join(str(value).lower() for value in slot_tags if value)
    return category in {"bar", "wine_bar"} or any(token in tag_text for token in ("jazz", "nightlife", "music"))


def _is_night_view_lock(item: dict[str, Any]) -> bool:
    if _is_locked_final_anchor(item):
        return True
    lock_text = _compact_source_text(
        " ".join(
            [
                str(item.get("slotLockReason") or ""),
                str(item.get("slotLockLabel") or ""),
                str(item.get("locked_label") or ""),
            ]
        )
    )
    return any(token in lock_text for token in ("night", "nightview", "sunset", "야경", "밤", "석양", "선셋"))


def _is_dinner_item(item: dict[str, Any]) -> bool:
    text = f"{item.get('time_slot') or ''} {item.get('title') or ''} {item.get('description') or ''}".lower()
    return "dinner" in text or "저녁" in text


def _is_late_bar_item(item: dict[str, Any]) -> bool:
    place = item.get("place") or {}
    category = str(place.get("category") or "").lower()
    tags = " ".join(str(value).lower() for value in place.get("tags") or [])
    cuisine = place.get("cuisine") or []
    if not isinstance(cuisine, list):
        cuisine = [cuisine]
    cuisine_text = " ".join(str(value).lower() for value in cuisine)
    text = " ".join([str(item.get("title") or "").lower(), tags, cuisine_text])
    return category in {"bar", "wine_bar"} or any(token in text for token in ("jazz", "nightlife", "wine", "재즈"))


def _preferred_start_minutes(item: dict[str, Any], role: str) -> int | None:
    preferred = _parse_clock_minutes(item.get("start_time"))
    if item.get("slotLockReason"):
        slot = str(item.get("time_slot") or "")
        if slot in _STRUCTURED_SLOT_MINUTES:
            return max(preferred or _STRUCTURED_SLOT_MINUTES[slot], _STRUCTURED_SLOT_MINUTES[slot])
    if role == "restaurant" and _is_lunch_item(item):
        if _is_brunch_item(item):
            return preferred or (11 * 60 + 15)
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


def _initial_day_start_minutes(
    items: list[dict[str, Any]],
    pace_level: str,
    preference_profile: dict[str, Any] | None = None,
) -> int:
    if not items:
        return DAY_START_MINUTES

    first_item = items[0]
    first_pref = _preferred_start_minutes(first_item, _role_key(first_item))
    lower_bound = max(DAY_START_MINUTES, first_pref or DAY_START_MINUTES)
    if _late_start_requested(preference_profile):
        lower_bound = max(lower_bound, 10 * 60 + 30)
    if first_pref is not None and str(first_item.get("time_slot") or "") == "morning" and first_item.get("slotLockReason"):
        return lower_bound

    required_before = 0
    latest_viable_starts: list[int] = []
    for index, item in enumerate(items):
        role = _role_key(item)
        if index > 0:
            preferred_start = _preferred_start_minutes(item, role)
            if preferred_start is not None:
                latest_viable_starts.append(preferred_start - required_before)
        required_before += _stay_duration_minutes(
            item,
            role,
            pace_level,
            low_walking=bool((preference_profile or {}).get("low_walking")),
        )
        required_before += _transfer_minutes_from_leg(item.get("route_to_next"))

    if not latest_viable_starts:
        return lower_bound

    latest_feasible = min(latest_viable_starts)
    if latest_feasible >= lower_bound:
        return latest_feasible
    return lower_bound


def _late_start_requested(preference_profile: dict[str, Any] | None) -> bool:
    if not isinstance(preference_profile, dict):
        return False
    brief = preference_profile.get("planning_brief") if isinstance(preference_profile.get("planning_brief"), dict) else {}
    compact = re.sub(r"\s+", "", str(brief.get("source_text") or "").lower())
    return any(
        token in compact
        for token in (
            "\uc544\uce68\uc77c\ucc0d\ub9d0\uace0",
            "\uc77c\ucc0d\uc2dc\uc791\ub9d0\uace0",
            "\uc77c\ucc0d\uc2dc\uc791\ud558\uc9c0\ub9d0\uace0",
            "\uc544\uce68\ub2a6\uac8c",
            "\ub2a6\uac8c\uc2dc\uc791",
            "\ube0c\ub7f0\uce58\ub85c\uc2dc\uc791",
            "\ube0c\ub7f0\uce58\ud6c4",
            "\ube0c\ub7f0\uce58\uba39\uace0",
            "startlate",
            "latestart",
            "brunchstart",
        )
    )


def _transfer_minutes_from_leg(route_to_next: Any) -> int:
    if not isinstance(route_to_next, dict):
        return 0
    return int(
        route_to_next.get("totalTransferMinutes")
        or round(int(route_to_next.get("scheduled_duration_seconds") or 0) / 60)
        or route_to_next.get("rawDurationMinutes")
        or max(1, round(int(route_to_next.get("duration_seconds") or 0) / 60))
    )


def _stay_duration_minutes(item: dict[str, Any], role: str, pace_level: str, *, low_walking: bool = False) -> int:
    if _is_lunch_item(item):
        base = 75
    elif role in {"restaurant", "meal_placeholder"}:
        base = STAY_DURATION_MINUTES["restaurant"]
    else:
        base = STAY_DURATION_MINUTES.get(role, 65)
    multiplier = PACE_DURATION_MULTIPLIER.get(pace_level, 1.0)
    adjusted = round(base * multiplier / 5) * 5
    if low_walking and _is_walk_like_item(item, role):
        return max(25, min(adjusted, 55))
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
    if preference_profile.get("low_walking"):
        if duration >= 90:
            return _copy(language, "Seated reset time", "\uc549\uc544\uc11c \uc26c\ub294 \uc5ec\uc720 \uc2dc\uac04")
        return _copy(language, "Short rest buffer", "\uc9e7\uc740 \ud734\uc2dd \ubc84\ud37c")
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
    if preference_profile.get("low_walking"):
        return _copy(
            language,
            "The user asked for low walking, so this is treated as seated recovery or a nearby cafe break instead of a long stroll.",
            "\ub9ce\uc774 \uac77\uae30 \uc2eb\ub2e4\ub294 \uc694\uccad\uc744 \ubc18\uc601\ud574, \uae34 \uc0b0\ucc45\uc774 \uc544\ub2c8\ub77c \uc549\uc544\uc11c \uc26c\uac70\ub098 \uac00\uae4c\uc6b4 \uce74\ud398\uc5d0\uc11c \ud68c\ubcf5\ud558\ub294 \uc2dc\uac04\uc73c\ub85c \ub450\uc5c8\uc2b5\ub2c8\ub2e4.",
        )
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
    minutes = min(max(0, minutes), 23 * 60 + 59)
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
    place = item.get("place") or {}
    category = str(place.get("category") or "").lower()
    if category in MEAL_PLACE_CATEGORIES or category == "meal_placeholder":
        return True
    title = f"{item.get('title') or ''} {item.get('description') or ''}".lower()
    slot = item.get("time_slot")
    if any(keyword in title for keyword in ["lunch", "dinner", "restaurant", "점심", "저녁", "식사"]):
        return True
    return slot == "lunch" and category in MEAL_PLACE_CATEGORIES


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
