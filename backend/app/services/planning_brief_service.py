from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from parser_api.parsers.shared.planning_brief_schema import ConstraintSpec, PlanningBriefPayload

SLOT_START_TIMES = {
    "morning": "09:00",
    "lunch": "12:00",
    "afternoon": "15:00",
    "evening": "18:30",
    "night": "20:30",
}

SLOT_END_TIMES = {
    "morning": "11:30",
    "lunch": "14:00",
    "afternoon": "17:30",
    "evening": "21:00",
    "night": "23:00",
}

MEAL_CATEGORIES = {"restaurant", "cafe", "bakery", "bistro", "brasserie", "wine_bar", "bar"}
HELPER_CATEGORIES = {"free_time", "meal_placeholder", "rest", "buffer", "helper_block"}
PLACE_ALIAS_GROUPS = (
    {"에펠탑", "에펠", "eiffel", "eiffeltower", "toureiffel"},
    {"루브르", "루브르박물관", "louvre", "louvremuseum", "louvrepyramid"},
    {"오르세", "오르세미술관", "orsay", "museedorsay"},
    {"개선문", "arc", "arcdetriomphe"},
    {"센강", "seine", "seineriver"},
    {"몽마르트르", "몽마르트", "montmartre", "sacrecoeur"},
    {"노트르담", "notredame", "notredamecathedral"},
    {"튈르리", "튈르리가든", "tuileries", "tuileriesgarden"},
    {"뤽상부르", "뤽상부르공원", "luxembourg", "luxembourggardens"},
    {"팔레가르니에", "가르니에", "palaisgarnier", "opera"},
)


def build_planning_brief(
    *,
    plan: dict[str, Any] | None = None,
    request: Any | None = None,
    trip: dict[str, Any] | None = None,
    intent: str = "create_trip",
    strict_constraints: bool = False,
) -> dict[str, Any]:
    plan = deepcopy(plan or {})
    trip = deepcopy(trip or {})
    preferences = plan.get("preferences") if isinstance(plan.get("preferences"), dict) else {}
    dates = plan.get("dates") if isinstance(plan.get("dates"), dict) else {}
    pace = plan.get("pace") if isinstance(plan.get("pace"), dict) else {}
    mobility = plan.get("mobility") if isinstance(plan.get("mobility"), dict) else {}
    budget = plan.get("budget") if isinstance(plan.get("budget"), dict) else {}
    lodging = plan.get("lodging") if isinstance(plan.get("lodging"), dict) else {}

    request_tags = list(getattr(request, "style_tags", []) or [])
    trip_tags = list(trip.get("style_tags") or [])
    source_text = " ".join(
        text
        for text in [
            str(plan.get("_source_message") or "").strip(),
            str(getattr(request, "prompt", "") or "").strip(),
            str(trip.get("prompt") or "").strip(),
        ]
        if text
    )
    travel_style = _merge_unique(
        list(preferences.get("travel_style") or []),
        list(preferences.get("themes") or []),
        request_tags,
        trip_tags,
    )
    must_include = _merge_unique(list(preferences.get("must_include") or []))
    must_avoid = _merge_unique(list(preferences.get("must_avoid") or []))
    preferred_time_slots = _merge_unique(list(preferences.get("preferred_time_slots") or []))
    meal_preference = _merge_unique(list(preferences.get("meal_preference") or []))
    must_include, must_avoid, preferred_time_slots, meal_preference, travel_style = _apply_text_fallbacks(
        source_text=source_text,
        must_include=must_include,
        must_avoid=must_avoid,
        preferred_time_slots=preferred_time_slots,
        meal_preference=meal_preference,
        travel_style=travel_style,
    )
    night_view_required = bool(preferences.get("night_view_required")) or "night_view" in travel_style or _has_night_view_signal(source_text)
    pace_level = str(pace.get("level") or _pace_from_tags(travel_style) or "normal").lower()
    if pace_level == "normal" and _has_slow_signal(source_text):
        pace_level = "slow"
    transport_preference = str(mobility.get("travel_mode") or "both").lower()
    start_time, end_time = _slot_window(preferred_time_slots)

    hard_constraints = [
        ConstraintSpec(
            id=f"must_include_{_slugify(value)}",
            type="must_include",
            value=value,
            priority="hard",
            source="user",
        )
        for value in must_include
    ]
    hard_constraints.extend(
        ConstraintSpec(
            id=f"must_avoid_{_slugify(value)}",
            type="must_avoid",
            value=value,
            priority="hard",
            source="user",
        )
        for value in must_avoid
    )
    if night_view_required:
        hard_constraints.append(
            ConstraintSpec(
                id="night_view_required",
                type="night_view_required",
                value=True,
                priority="hard",
                source="user",
            )
        )

    soft_constraints = []
    if preferred_time_slots:
        soft_constraints.append(
            ConstraintSpec(
                id="preferred_time_slots",
                type="preferred_time_slots",
                value=preferred_time_slots,
                priority="soft",
                source="user",
            )
        )
    if meal_preference:
        soft_constraints.append(
            ConstraintSpec(
                id="meal_preference",
                type="meal_preference",
                value=meal_preference,
                priority="soft",
                source="user",
            )
        )
    if travel_style:
        soft_constraints.append(
            ConstraintSpec(
                id="travel_style",
                type="travel_style",
                value=travel_style,
                priority="soft",
                source="parser",
            )
        )
    if pace_level:
        soft_constraints.append(
            ConstraintSpec(
                id="pace",
                type="pace",
                value=pace_level,
                priority="soft",
                source="parser",
            )
        )

    payload = PlanningBriefPayload(
        intent=intent,
        trip_days=int(dates.get("days") or trip.get("total_days") or getattr(request, "total_days", None) or 0) or None,
        destination=str((plan.get("destination") or {}).get("city") or "Paris"),
        must_include=must_include,
        must_avoid=must_avoid,
        preferred_time_slots=preferred_time_slots,
        meal_preference=meal_preference,
        night_view_required=night_view_required,
        pace=pace_level,
        travel_style=travel_style,
        budget_range={
            "currency": budget.get("currency") or "EUR",
            "budget_total": budget.get("budget_total"),
            "budget_per_day": budget.get("budget_per_day"),
            "budget_mode": budget.get("budget_mode") or "normal",
        },
        hotel_area_preference=str(lodging.get("text") or "").strip() or None,
        transport_preference=transport_preference,
        start_time=start_time,
        end_time=end_time,
        hard_constraints=hard_constraints,
        soft_constraints=soft_constraints,
        strict_constraints=strict_constraints,
        locked_stops=_derive_locked_stops(must_include, night_view_required, source_text),
        preferred_blueprints=_derive_preferred_blueprints(
            pace=pace_level,
            travel_style=travel_style,
            meal_preference=meal_preference,
            night_view_required=night_view_required,
            must_include=must_include,
            preferred_time_slots=preferred_time_slots,
        ),
    )
    return payload.model_dump(mode="json")


def extract_planning_brief(source: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(source, dict):
        return None
    brief = source.get("planning_brief")
    if isinstance(brief, dict):
        return deepcopy(brief)
    trip = source.get("trip")
    if isinstance(trip, dict) and isinstance(trip.get("planning_brief"), dict):
        return deepcopy(trip["planning_brief"])
    return None


def validate_planning_brief_compliance(
    itinerary_days: list[dict[str, Any]],
    planning_brief: dict[str, Any] | None,
) -> dict[str, Any]:
    brief = planning_brief or {}
    real_items = _real_items(itinerary_days)
    normalized_catalog = [_item_search_text(item) for item in real_items]

    must_include = [str(value) for value in brief.get("must_include") or [] if str(value).strip()]
    must_avoid = [str(value) for value in brief.get("must_avoid") or [] if str(value).strip()]
    preferred_slots = {str(value) for value in brief.get("preferred_time_slots") or [] if str(value)}
    meal_preferences = [str(value).lower() for value in brief.get("meal_preference") or [] if str(value).strip()]
    pace = str(brief.get("pace") or "normal").lower()
    travel_style = {str(value).lower() for value in brief.get("travel_style") or [] if str(value).strip()}

    missing_must_include = [value for value in must_include if not _constraint_matches_catalog(value, normalized_catalog)]
    included_must_avoid = [value for value in must_avoid if _constraint_matches_catalog(value, normalized_catalog)]

    time_slot_violations: list[str] = []
    if brief.get("night_view_required"):
        has_night_view = any(
            bool(item.get("isNightViewSpot"))
            or (
                str(item.get("time_slot") or "") in {"evening", "night"}
                and any(token in _normalize_name(str((item.get("place") or {}).get("name") or item.get("title") or "")) for token in ("eiffel", "seine", "arc", "louvre", "몽마르트", "센강", "에펠", "개선문"))
            )
            for item in real_items
        )
        if not has_night_view:
            time_slot_violations.append("night_view_required")

    if preferred_slots and not any(str(item.get("time_slot") or "") in preferred_slots for item in real_items):
        time_slot_violations.append("preferred_time_slots")

    meal_preference_violations: list[str] = []
    meal_items = [item for item in real_items if _is_meal_item(item)]
    if any(item.get("nearbyMealNeeded") for item in real_items):
        meal_preference_violations.append("nearbyMealNeeded")
    if meal_items:
        for item in meal_items:
            category = str(((item.get("place") or {}).get("category")) or "").lower()
            if category not in MEAL_CATEGORIES:
                meal_preference_violations.append(str(item.get("title") or "meal_category"))
    if meal_preferences:
        meal_haystack = " ".join(
            " ".join(
                [
                    str((item.get("place") or {}).get("name") or item.get("title") or ""),
                    str((item.get("place") or {}).get("category") or ""),
                    " ".join(str(value) for value in ((item.get("place") or {}).get("cuisine") or []) if value),
                    str(item.get("description") or ""),
                ]
            )
            for item in meal_items
        ).lower()
        if any(token in travel_style for token in {"cafe", "dessert", "foodie"}) and not any(keyword in meal_haystack for keyword in ("cafe", "coffee", "dessert", "bakery", "cake")):
            meal_preference_violations.append("cafe_dessert_preference")
        if any("french" in preference for preference in meal_preferences) and "french" not in meal_haystack and "brasserie" not in meal_haystack and "bistro" not in meal_haystack:
            meal_preference_violations.append("french_meal_preference")

    pace_violations: list[str] = []
    quality_violations: list[str] = []
    warnings: list[str] = []
    strict_constraints = bool(brief.get("strict_constraints"))
    total_helper_minutes = 0
    total_real_items = 0
    total_high_burden_count = 0
    has_cafe_dessert_anchor = False
    has_french_dinner = False
    has_night_climax = False
    for day in itinerary_days:
        day_items = _real_items([day])
        helper_items = [item for item in day.get("items") or [] if _is_helper_item(item)]
        total_real_items += len(day_items)
        high_burden_count = sum(
            1
            for item in day_items
            if isinstance(item.get("route_to_next"), dict) and str((item.get("route_to_next") or {}).get("effort_level") or "") == "high"
        )
        total_high_burden_count += high_burden_count
        helper_gap_minutes = sum(int(item.get("duration_minutes") or 0) for item in helper_items)
        total_helper_minutes += helper_gap_minutes
        helper_item_count = len(helper_items)
        longest_helper_block = max((int(item.get("duration_minutes") or 0) for item in helper_items), default=0)
        if helper_gap_minutes >= 90:
            quality_violations.append(f"day_{day.get('day_number')}_helper_block_ratio")
        real_meal_items = [item for item in day_items if _is_meal_item(item)]
        if any(
            str(((item.get("place") or {}).get("category")) or "").lower() in {"cafe", "bakery"}
            or any(
                token in _normalize_name(
                    " ".join(
                        [
                            str((item.get("place") or {}).get("name") or ""),
                            " ".join(str(value) for value in ((item.get("place") or {}).get("cuisine") or []) if value),
                            str(item.get("description") or ""),
                        ]
                    )
                )
                for token in ("cafe", "coffee", "dessert", "cake", "bakery", "patisserie", "croissant")
            )
            for item in day_items
        ):
            has_cafe_dessert_anchor = True
        if any(
            str(item.get("time_slot") or "") == "evening"
            and (
                str(((item.get("place") or {}).get("category")) or "").lower() in {"restaurant", "bistro", "brasserie", "bar"}
                or any(
                    token in _normalize_name(
                        " ".join(
                            [
                                str((item.get("place") or {}).get("name") or ""),
                                " ".join(str(value) for value in ((item.get("place") or {}).get("cuisine") or []) if value),
                                str(item.get("description") or ""),
                            ]
                        )
                    )
                    for token in ("french", "bistro", "brasserie", "wine")
                )
            )
            for item in real_meal_items
        ):
            has_french_dinner = True
        if day_items and bool(day_items[-1].get("isNightViewSpot")):
            has_night_climax = True
        if pace == "slow":
            max_places = 5 if strict_constraints else 6
            if len(day_items) > max_places:
                pace_violations.append(f"day_{day.get('day_number')}_too_many_places")
            if high_burden_count > 1:
                pace_violations.append(f"day_{day.get('day_number')}_high_transfer")
        if helper_item_count > 2:
            quality_violations.append(f"day_{day.get('day_number')}_helper_block_count")
        if helper_gap_minutes > 90:
            quality_violations.append(f"day_{day.get('day_number')}_helper_block_minutes")
        elif helper_gap_minutes > 45:
            warnings.append(f"day_{day.get('day_number')}_long_helper_time")
        if longest_helper_block >= 120:
            quality_violations.append(f"day_{day.get('day_number')}_single_helper_block")

    if brief.get("night_view_required") and not has_night_climax:
        quality_violations.append("night_climax_missing")

    if any(token in travel_style for token in {"cafe", "dessert", "foodie"}) and not has_cafe_dessert_anchor:
        meal_preference_violations.append("cafe_dessert_underrepresented")

    if any("french" in preference for preference in meal_preferences) and not has_french_dinner:
        meal_preference_violations.append("french_dinner_underrepresented")

    satisfied_constraints = []
    violated_constraints = []
    if not missing_must_include:
        satisfied_constraints.append("must_include")
    else:
        violated_constraints.append("must_include")
    if not included_must_avoid:
        satisfied_constraints.append("must_avoid")
    else:
        violated_constraints.append("must_avoid")
    if not time_slot_violations:
        satisfied_constraints.append("time_slots")
    else:
        violated_constraints.append("time_slots")
    if not meal_preference_violations:
        satisfied_constraints.append("meal_preferences")
    else:
        violated_constraints.append("meal_preferences")
    if not pace_violations:
        satisfied_constraints.append("pace")
    else:
        violated_constraints.append("pace")
    if not quality_violations:
        satisfied_constraints.append("story_flow")
    else:
        violated_constraints.append("story_flow")

    severe_violations = bool(
        missing_must_include
        or included_must_avoid
        or "night_view_required" in time_slot_violations
        or "nearbyMealNeeded" in meal_preference_violations
        or quality_violations
    )
    constraint_denom = max(
        1,
        len(must_include)
        + len(must_avoid)
        + int(bool(brief.get("night_view_required")))
        + int(bool(preferred_slots)),
    )
    hard_failures = (
        len(missing_must_include)
        + len(included_must_avoid)
        + int("night_view_required" in time_slot_violations)
        + int("preferred_time_slots" in time_slot_violations)
    )
    constraint_score = max(0.0, 1.0 - (hard_failures / constraint_denom))
    preference_penalties = len(meal_preference_violations) + len([value for value in time_slot_violations if value != "night_view_required"])
    preference_base = max(1, len(meal_preferences) + len(preferred_slots) + int(any(token in travel_style for token in {"cafe", "dessert", "foodie"})))
    preference_match_score = max(0.0, 1.0 - (preference_penalties / preference_base))
    pacing_penalties = len(pace_violations)
    pacing_score = max(0.0, 1.0 - (pacing_penalties / max(1, len(itinerary_days))))
    route_penalty = min(0.5, total_high_burden_count * 0.12)
    route_score = max(0.0, 1.0 - route_penalty)
    helper_ratio = total_helper_minutes / max(1, (total_real_items * 90) + total_helper_minutes)
    helper_penalty = min(0.35, round(helper_ratio * 0.75, 3))
    story_flow_score = 1.0
    if warnings:
        story_flow_score -= 0.12
    if quality_violations:
        story_flow_score -= min(0.45, 0.12 * len(set(quality_violations)))
    story_flow_score = max(0.0, round(story_flow_score, 2))
    final_quality_score = round(
        (constraint_score * 0.35)
        + (preference_match_score * 0.20)
        + (story_flow_score * 0.20)
        + (pacing_score * 0.15)
        + (route_score * 0.10)
        - helper_penalty,
        2,
    )
    is_valid = not severe_violations and not violated_constraints and final_quality_score >= 0.75
    return {
        "is_valid": is_valid,
        "score": final_quality_score,
        "constraint_score": round(constraint_score, 2),
        "preference_match_score": round(preference_match_score, 2),
        "route_score": round(route_score, 2),
        "pacing_score": round(pacing_score, 2),
        "helper_penalty": helper_penalty,
        "story_flow_score": story_flow_score,
        "final_quality_score": final_quality_score,
        "satisfied_constraints": satisfied_constraints,
        "violated_constraints": violated_constraints,
        "missing_must_include": missing_must_include,
        "included_must_avoid": included_must_avoid,
        "time_slot_violations": time_slot_violations,
        "meal_preference_violations": meal_preference_violations,
        "pace_violations": pace_violations,
        "quality_violations": quality_violations,
        "warnings": warnings,
        "needs_replan": severe_violations or bool(violated_constraints) or final_quality_score < 0.75 or story_flow_score < 0.72,
    }


def mark_constraint_attempt(
    planning_brief: dict[str, Any],
    attempt: int,
    reason: str,
    action: str,
    *,
    previous_blueprints: list[str] | None = None,
) -> dict[str, Any]:
    brief = deepcopy(planning_brief)
    next_blueprints = _select_replan_blueprints(brief, reason, previous_blueprints or [])
    history = list(brief.get("replan_history") or [])
    history.append(
        {
            "attempt": attempt,
            "reason": reason,
            "action": action,
            "previous_blueprint": (previous_blueprints or [None])[0],
            "next_blueprint": next_blueprints[0] if next_blueprints else None,
        }
    )
    brief["replan_history"] = history
    brief["strict_constraints"] = True
    if next_blueprints:
        brief["preferred_blueprints"] = next_blueprints
    brief["locked_stops"] = _derive_locked_stops(
        [str(value) for value in brief.get("must_include") or [] if str(value).strip()],
        bool(brief.get("night_view_required")),
        "",
    )
    if action == "reduce_helper_blocks_and_rebuild":
        preferred = _merge_unique(list(brief.get("preferred_time_slots") or []), ["afternoon"])
        brief["preferred_time_slots"] = preferred
        brief["start_time"], brief["end_time"] = _slot_window(preferred)
        brief["quality_focus"] = "reduce_helper_blocks"
    if action in {"lock_eiffel_tower_to_night_slot", "switch_to_evening_first_blueprint"}:
        preferred = _merge_unique(list(brief.get("preferred_time_slots") or []), ["afternoon", "evening", "night"])
        brief["preferred_time_slots"] = preferred
        brief["start_time"], brief["end_time"] = _slot_window(preferred)
    return brief


def _real_items(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for day in days:
        for item in day.get("items") or []:
            if _is_helper_item(item) or item.get("nearbyMealNeeded"):
                continue
            items.append(item)
    return items


def _is_meal_item(item: dict[str, Any]) -> bool:
    if _is_helper_item(item):
        return False
    slot = str(item.get("time_slot") or "")
    category = str(((item.get("place") or {}).get("category")) or "").lower()
    title = str(item.get("title") or "").lower()
    if category in MEAL_CATEGORIES:
        return True
    return slot == "lunch" or any(token in title for token in ("점심", "저녁", "lunch", "dinner"))


def _slot_window(preferred_slots: list[str]) -> tuple[str | None, str | None]:
    normalized = [slot for slot in preferred_slots if slot in SLOT_START_TIMES]
    if not normalized:
        return None, None
    start_slot = min(normalized, key=lambda slot: list(SLOT_START_TIMES).index(slot))
    end_slot = max(normalized, key=lambda slot: list(SLOT_START_TIMES).index(slot))
    return SLOT_START_TIMES[start_slot], SLOT_END_TIMES[end_slot]


def _pace_from_tags(tags: list[str]) -> str | None:
    lowered = {str(tag).lower() for tag in tags}
    if lowered.intersection({"slow", "relaxed", "healing", "여유", "휴식"}):
        return "slow"
    if lowered.intersection({"fast", "packed", "busy"}):
        return "fast"
    return None


def _apply_text_fallbacks(
    *,
    source_text: str,
    must_include: list[str],
    must_avoid: list[str],
    preferred_time_slots: list[str],
    meal_preference: list[str],
    travel_style: list[str],
) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    lowered = source_text.lower()
    next_must_include = list(must_include)
    next_must_avoid = list(must_avoid)
    next_preferred_time_slots = list(preferred_time_slots)
    next_meal_preference = list(meal_preference)
    next_travel_style = list(travel_style)

    if not next_must_include and ("에펠" in source_text or "eiffel" in lowered):
        next_must_include = _merge_unique(next_must_include, ["에펠탑"])
    if ("루브르" in source_text or "louvre" in lowered) and any(
        token in lowered for token in ("말고", "제외", "않", "싫", "avoid", "without", "don't", "dont")
    ):
        next_must_avoid = _merge_unique(next_must_avoid, ["루브르 박물관"])
    if _has_night_view_signal(source_text):
        next_travel_style = _merge_unique(next_travel_style, ["night_view"])
        next_preferred_time_slots = _merge_unique(next_preferred_time_slots, ["evening", "night"])
    if any(token in lowered for token in ("cafe", "coffee", "카페")):
        next_meal_preference = _merge_unique(next_meal_preference, ["cafe"])
        next_travel_style = _merge_unique(next_travel_style, ["foodie"])
    if any(token in lowered for token in ("dessert", "bakery", "디저트", "베이커리")):
        next_meal_preference = _merge_unique(next_meal_preference, ["dessert"])
        next_travel_style = _merge_unique(next_travel_style, ["foodie"])
    if any(token in lowered for token in ("french", "프렌치", "브라세리", "비스트로")):
        next_meal_preference = _merge_unique(next_meal_preference, ["french"])
    if _has_slow_signal(source_text):
        next_travel_style = _merge_unique(next_travel_style, ["slow"])
    return next_must_include, next_must_avoid, next_preferred_time_slots, next_meal_preference, next_travel_style


def _has_night_view_signal(source_text: str) -> bool:
    lowered = source_text.lower()
    return any(token in lowered for token in ("night view", "night_view", "sparkling", "야경", "석양", "선셋", "야간"))


def _has_slow_signal(source_text: str) -> bool:
    lowered = source_text.lower()
    return any(token in lowered for token in ("slow", "relax", "relaxed", "healing", "천천히", "여유", "느긋", "많이 돌아다니는 건 싫"))


def _derive_locked_stops(must_include: list[str], night_view_required: bool, source_text: str) -> list[dict[str, Any]]:
    if not night_view_required and not _has_night_view_signal(source_text):
        return []
    locks: list[dict[str, Any]] = []
    for value in must_include:
        aliases = _constraint_aliases(value)
        if aliases.intersection({"에펠탑", "에펠", "eiffel", "eiffeltower", "toureiffel"}):
            locks.append(
                {
                    "entity": "eiffel_tower",
                    "slug": "eiffel-tower",
                    "modifier": "night_view",
                    "target_slot": "evening",
                    "locked": True,
                    "preferred_day": 1,
                    "label": "에펠탑 야경",
                }
            )
        elif aliases.intersection({"센강", "seine", "seineriver"}):
            locks.append(
                {
                    "entity": "seine_river",
                    "slug": "seine-river-walk",
                    "modifier": "night_view",
                    "target_slot": "night",
                    "locked": True,
                    "preferred_day": 1,
                    "label": "센강 야경 산책",
                }
            )
        elif aliases.intersection({"개선문", "arc", "arcdetriomphe"}):
            locks.append(
                {
                    "entity": "arc_de_triomphe",
                    "slug": "arc-de-triomphe",
                    "modifier": "night_view",
                    "target_slot": "evening",
                    "locked": True,
                    "preferred_day": 1,
                    "label": "개선문 야경",
                }
            )
    return locks


def _derive_preferred_blueprints(
    *,
    pace: str,
    travel_style: list[str],
    meal_preference: list[str],
    night_view_required: bool,
    must_include: list[str],
    preferred_time_slots: list[str],
) -> list[str]:
    normalized_style = {str(value).lower() for value in travel_style if str(value).strip()}
    normalized_meal = {str(value).lower() for value in meal_preference if str(value).strip()}
    normalized_must_include = " ".join(str(value).lower() for value in must_include if str(value).strip())
    prefers_cafe_dessert = bool(normalized_style.intersection({"cafe", "dessert", "foodie"})) or bool(
        normalized_meal.intersection({"cafe", "dessert", "coffee", "bakery"})
    )
    prefers_french_dinner = bool(normalized_meal.intersection({"french", "bistro", "brasserie", "romantic"}))
    has_eiffel_night = "에펠" in normalized_must_include or "eiffel" in normalized_must_include
    late_start = bool(set(preferred_time_slots).intersection({"afternoon", "evening", "night"}))

    if pace == "slow" and prefers_cafe_dessert and night_view_required and has_eiffel_night and prefers_french_dinner:
        return ["slow_cafe_evening_day", "romantic_evening_day", "slow_cafe_day"]
    if night_view_required and has_eiffel_night:
        return ["night_view_focused_day", "romantic_evening_day", "general_landmark_day"]
    if pace == "slow" and prefers_cafe_dessert:
        return ["slow_cafe_day", "romantic_evening_day" if late_start else "general_landmark_day"]
    if night_view_required:
        return ["romantic_evening_day", "night_view_focused_day"]
    return []


def _select_replan_blueprints(
    planning_brief: dict[str, Any],
    reason: str,
    previous_blueprints: list[str],
) -> list[str]:
    current = list(planning_brief.get("preferred_blueprints") or [])
    if current:
        base = list(current)
    else:
        base = _derive_preferred_blueprints(
            pace=str(planning_brief.get("pace") or "normal"),
            travel_style=list(planning_brief.get("travel_style") or []),
            meal_preference=list(planning_brief.get("meal_preference") or []),
            night_view_required=bool(planning_brief.get("night_view_required")),
            must_include=list(planning_brief.get("must_include") or []),
            preferred_time_slots=list(planning_brief.get("preferred_time_slots") or []),
        )
    lowered = reason.lower()
    if any(token in lowered for token in ("must_include", "night_view", "nightclimax", "night_climax", "에펠")):
        next_base = ["slow_cafe_evening_day", "romantic_evening_day", "night_view_focused_day"]
    elif any(token in lowered for token in ("helper", "story_flow", "quality")):
        next_base = ["slow_cafe_evening_day", "slow_cafe_day", "romantic_evening_day"]
    else:
        next_base = base or ["general_landmark_day"]
    if previous_blueprints and next_base and previous_blueprints[0] == next_base[0]:
        rotations = ["romantic_evening_day", "night_view_focused_day", "slow_cafe_day", "general_landmark_day"]
        for candidate in rotations:
            if candidate != previous_blueprints[0]:
                next_base = [candidate, *[value for value in next_base if value != candidate]]
                break
    return list(dict.fromkeys(next_base))


def _merge_unique(*groups: list[Any]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in group or []:
            text = str(value).strip()
            if text and text not in seen:
                merged.append(text)
                seen.add(text)
    return merged


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9가-힣]+", "_", value.lower()).strip("_") or "constraint"


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9가-힣]+", "", value.lower())


def _item_search_text(item: dict[str, Any]) -> str:
    place = item.get("place") or {}
    values = [
        str(place.get("name") or ""),
        str(item.get("title") or ""),
        str(place.get("category") or ""),
        str(item.get("description") or ""),
    ]
    cuisine = place.get("cuisine")
    if isinstance(cuisine, list):
        values.extend(str(value) for value in cuisine if value)
    elif cuisine:
        values.append(str(cuisine))
    return _normalize_name(" ".join(values))


def _constraint_matches_catalog(value: str, catalog: list[str]) -> bool:
    aliases = _constraint_aliases(value)
    for entry in catalog:
        if not entry:
            continue
        if any(alias in entry or entry in alias for alias in aliases):
            return True
    return False


def _constraint_aliases(value: str) -> set[str]:
    normalized = _normalize_name(value)
    aliases = {normalized}
    for group in PLACE_ALIAS_GROUPS:
        if any(alias in normalized or normalized in alias for alias in group if alias):
            aliases.update(group)
    return {alias for alias in aliases if alias}


def _is_helper_item(item: dict[str, Any]) -> bool:
    if item.get("itemKind") == "gap":
        return True
    place = item.get("place") or {}
    category = str(place.get("category") or "").lower()
    title = _normalize_name(str(item.get("title") or place.get("name") or ""))
    return category in HELPER_CATEGORIES or any(
        token in title
        for token in (
            "자유시간",
            "카페휴식",
            "재정비",
            "여유산책",
            "점심전",
            "저녁전",
            "photobrowsetime",
            "slowcafebreak",
            "freetimebeforelunch",
            "resetbeforedinner",
            "hotelresetorcheckin",
        )
    )
