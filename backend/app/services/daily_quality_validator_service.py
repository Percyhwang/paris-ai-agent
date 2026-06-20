from __future__ import annotations

import math
import re
from typing import Any

from app.services.planning_brief_service import extract_user_request_text


MEAL_CATEGORIES = {"restaurant", "bistro", "brasserie", "bar", "wine_bar", "cafe", "bakery"}
CAFE_CATEGORIES = {"cafe", "bakery"}
RESTAURANT_CATEGORIES = {"restaurant", "bistro", "brasserie", "bar", "wine_bar"}
ART_CATEGORIES = {"museum", "gallery"}
MAIN_ACTIVITY_CATEGORIES = {"museum", "gallery", "landmark", "cathedral", "shopping"}
HIGH_INTENSITY_CATEGORIES = {"museum", "gallery", "landmark", "cathedral", "shopping"}
LOW_INTENSITY_ROLES = {"walking_route", "cafe_break", "dessert", "lunch", "dinner", "night_activity"}
TOURIST_HEAVY_CATEGORIES = {"museum", "gallery", "landmark", "cathedral", "shopping"}
LOCAL_SUPPORT_CATEGORIES = {"neighborhood", "park", "cafe", "bakery"}
FAMILY_UNFRIENDLY_CATEGORIES = {"bar", "wine_bar"}
CORE_TRIP_CONCEPTS = {"romantic", "landmark", "art", "shopping", "local", "night_view", "foodie", "cafe", "family"}
GENERIC_THEME_PHRASES = {
    "a paris day flowing",
    "파리의 흐름을 따라",
    "파리 하루",
    "파리 일정",
    "day paris plan",
    "classic paris",
    "클래식 파리",
}
GENERIC_DESCRIPTION_PHRASES = (
    "slow pace",
    "relaxing atmosphere",
    "하루 흐름",
    "파리의 흐름",
    "느긋한 분위기",
    "분위기를 지탱",
    "중간 정차점",
)
QUALITY_WEIGHTS = {
    "user_intent_match": 25.0,
    "category_diversity": 20.0,
    "meal_timing_quality": 15.0,
    "theme_coherence": 15.0,
    "route_efficiency": 10.0,
    "experience_value": 10.0,
    "description_quality": 5.0,
}
CATEGORY_EXCLUSION_HINTS = {
    "cafe": ("카페 제외", "카페 빼", "no cafe", "without cafe", "skip cafe"),
    "restaurant": ("식당 제외", "레스토랑 제외", "no restaurant", "without restaurant"),
    "shopping": ("쇼핑 제외", "쇼핑 빼", "no shopping", "without shopping"),
    "museum": ("미술관 제외", "박물관 제외", "museum 제외", "no museum", "without museum"),
}


def evaluate_itinerary_quality(
    itinerary_days: list[dict[str, Any]],
    planning_brief: dict[str, Any] | None,
    *,
    prompt: str = "",
    language: str = "ko",
) -> dict[str, Any]:
    del language
    prompt = extract_user_request_text(prompt)
    brief = planning_brief or {}
    trip_day_count = max(len(itinerary_days), 1)
    day_reports = [
        _evaluate_day_quality(
            day,
            brief,
            prompt=prompt,
            trip_day_count=trip_day_count,
        )
        for day in itinerary_days
    ]
    trip_breakdown = _aggregate_breakdown(day_reports)
    trip_score = round(sum(trip_breakdown.values()), 2)
    issue_details = [
        {
            **issue,
            "message": f"Day {day_report.get('day_number')}: {issue['message']}",
        }
        for day_report in day_reports
        for issue in day_report.get("issue_details") or []
    ]
    trip_warnings: list[str] = []
    trip_warning_details: list[dict[str, Any]] = []
    requested_concepts = _requested_trip_concepts(brief, prompt)
    matched_concepts, missing_concepts = _matched_trip_concepts(itinerary_days, requested_concepts)

    if len(day_reports) >= 2:
        theme_signatures = {_theme_signature(day.get("theme") or "") for day in day_reports if str(day.get("theme") or "").strip()}
        if len(theme_signatures) <= 1:
            warning = "Multiple days share the same generic theme signature."
            trip_warnings.append(warning)
            trip_warning_details.append(
                {
                    "code": "trip_theme_repetition",
                    "message": warning,
                    "repair": "Regenerate at least one day theme around a different main activity or neighborhood.",
                    "severity": "warning",
                }
            )

    if requested_concepts and _trip_concept_coverage_is_weak(requested_concepts, matched_concepts):
        missing_label = ", ".join(missing_concepts[:4]) or ", ".join(sorted(requested_concepts)[:4])
        warning = f"Requested trip concepts are underrepresented across the itinerary: {missing_label}."
        trip_warning_details.append(
            {
                "code": "concept_mismatch",
                "message": warning,
                "repair": "Rebalance the itinerary so requested concepts appear as real activities, meals, walks, shopping blocks, or evening anchors across the trip.",
                "severity": "error",
                "target": missing_label,
            }
        )

    errors = [detail["message"] for detail in issue_details if detail.get("severity") == "error"]
    warnings = [
        *(detail["message"] for detail in issue_details if detail.get("severity") == "warning"),
        *trip_warnings,
    ]
    repair_suggestions = list(
        dict.fromkeys(
            [
                *(detail.get("repair") for detail in issue_details if str(detail.get("repair") or "").strip()),
                *(detail.get("repair") for detail in trip_warning_details if str(detail.get("repair") or "").strip()),
            ]
        )
    )

    return {
        "passed": bool(day_reports) and all(bool(day.get("passed")) for day in day_reports) and trip_score >= 80.0,
        "score": trip_score,
        "errors": errors,
        "warnings": warnings,
        "repair_suggestions": repair_suggestions,
        "days": day_reports,
        "score_breakdown": trip_breakdown,
        "issue_details": [*issue_details, *trip_warning_details],
        "requested_concepts": sorted(requested_concepts),
        "matched_concepts": sorted(matched_concepts),
    }


def _evaluate_day_quality(
    day: dict[str, Any],
    brief: dict[str, Any],
    *,
    prompt: str,
    trip_day_count: int,
) -> dict[str, Any]:
    theme = str(day.get("dayTheme") or day.get("theme") or day.get("title") or "").strip()
    items = [_normalize_item(item) for item in day.get("items") or [] if item.get("itemKind") != "gap"]
    issue_details: list[dict[str, Any]] = []
    bad_patterns: list[str] = []

    categories = [item["category"] for item in items if item["category"]]
    distinct_categories = len(set(categories))
    cafe_count = sum(1 for item in items if item["is_cafe"])
    meal_like_count = sum(1 for item in items if item["is_meal"] or item["is_cafe"])
    art_count = sum(1 for item in items if item["is_art_or_culture"])
    museum_like_count = sum(1 for item in items if item["category"] in ART_CATEGORIES or item["role"] == "museum_or_gallery")
    experience_stop_count = sum(1 for item in items if _counts_as_experience_stop(item))
    role_variety = len({item["role"] for item in items if item["role"]})
    meal_dominant = bool(items) and meal_like_count >= max(3, math.ceil(len(items) * 0.6))
    repeated_category_count = _max_consecutive_category_count(categories)
    consecutive_cafe_count = _max_consecutive_true(items, lambda item: item["is_cafe"])
    nightlife_requested = _nightlife_requested(brief, prompt)
    consecutive_restaurant_chain = _has_consecutive_restaurant_chain(items, nightlife_requested=nightlife_requested)
    pace_min, pace_max, pace_label = _pace_bounds(brief, items)
    fatigue_break_missing = _has_fatigue_break_issue(items)
    overloaded_night_tail = _night_tail_is_overloaded(items)
    excluded_categories = _excluded_categories(brief, prompt)
    present_excluded = sorted({item["category"] for item in items if item["category"] in excluded_categories})
    art_required = _art_trip_requested(brief, prompt)
    art_day_required = art_required and (
        trip_day_count <= 2 or _theme_requests_art(theme)
    )
    family_requested = _family_trip_requested(brief, prompt)
    local_requested = _local_mood_requested(brief, prompt)
    brunch_requested = _brunch_requested(brief, prompt)
    main_activity_count = sum(1 for item in items if _counts_as_main_activity(item, local_requested=local_requested))
    lunch_item = next((item for item in items if item["role"] == "lunch"), None)
    brunch_item = next((item for item in items if _is_brunch_item(item)), None) if brunch_requested else None
    if lunch_item is None and brunch_item is not None:
        lunch_item = brunch_item
    lunch_ok = False
    if lunch_item is not None:
        if brunch_requested and _is_brunch_item(lunch_item):
            lunch_ok = _within_window(lunch_item["start_minutes"], 10 * 60 + 30, 13 * 60 + 30)
        else:
            lunch_ok = _within_window(lunch_item["start_minutes"], 12 * 60, 14 * 60 + 30)
    dinner_item = next((item for item in items if item["role"] == "dinner"), None)
    dinner_ok = dinner_item is not None and _within_window(dinner_item["start_minutes"], 18 * 60 + 30, 21 * 60)
    tourist_avoid_requested = _tourist_avoid_requested(brief, prompt)
    museum_limit = _museum_limit_per_day(brief)
    family_unsuitable_titles = _family_unsuitable_titles(items) if family_requested else []
    tourist_heavy_titles = [item["title"] for item in items if item["category"] in TOURIST_HEAVY_CATEGORIES]
    local_support_count = sum(
        1
        for item in items
        if item["category"] in LOCAL_SUPPORT_CATEGORIES or item["role"] == "walking_route"
    )
    touristiness_mismatch = _has_touristiness_mismatch(
        items,
        local_requested=local_requested,
        tourist_avoid_requested=tourist_avoid_requested,
    )
    generic_description_count = _generic_description_count(items)
    duplicate_description_ratio = _duplicate_description_ratio(items)

    if cafe_count >= 3:
        issue_details.append(
            _issue(
                "too_many_cafes",
                f"Day has {cafe_count} cafe-like stops; cap cafe breaks at 2.",
                "Replace extra cafe breaks with a walk, landmark, shopping, or a single stronger main activity.",
                severity="error",
            )
        )
        bad_patterns.append("too_many_cafes")

    if consecutive_cafe_count >= 2:
        issue_details.append(
            _issue(
                "consecutive_cafe_chain",
                "Cafe-style stops are placed back-to-back, which makes the day feel repetitive.",
                "Insert a walk, museum, shopping, or landmark stop between cafe breaks.",
                severity="error",
            )
        )
        bad_patterns.append("consecutive_cafe_chain")

    if consecutive_restaurant_chain:
        issue_details.append(
            _issue(
                "consecutive_restaurant_chain",
                "Restaurant-style stops are consecutive instead of being separated by a real activity.",
                "Keep meals in their natural windows and place a walk, landmark, or main activity between them.",
                severity="error",
            )
        )
        bad_patterns.append("consecutive_restaurant_chain")

    if repeated_category_count > 2:
        issue_details.append(
            _issue(
                "repetitive_category",
                "The same category repeats more than twice in a row.",
                "Break the repetition by inserting a different experience type between similar stops.",
                severity="error",
            )
        )
        bad_patterns.append("repetitive_category_run")

    if main_activity_count < 1:
        issue_details.append(
            _issue(
                "main_activity_missing",
                "The day has no clear main activity.",
                "Add a museum, landmark, gallery, or shopping anchor as the day's main activity.",
                severity="error",
            )
        )
        bad_patterns.append("missing_main_activity")

    if distinct_categories < 3:
        issue_details.append(
            _issue(
                "low_category_diversity",
                f"Only {distinct_categories} distinct categories appear in the day.",
                "Increase category diversity with at least one walk/landmark/local block between meals and breaks.",
                severity="error",
            )
        )

    if len(items) < pace_min or len(items) > pace_max:
        issue_details.append(
            _issue(
                "pace_density_mismatch",
                f"Day has {len(items)} real stops; {pace_label} pace should stay around {pace_min}-{pace_max} stops.",
                "Add or trim stops so the day density matches the requested travel style without breaking meal timing.",
                severity="error",
            )
        )
        bad_patterns.append("pace_density_mismatch")

    if lunch_item is not None and not lunch_ok:
        issue_details.append(
            _issue(
                "lunch_timing_bad",
                (
                    f"Brunch is scheduled at {lunch_item['start_time']}, outside the 10:30-13:30 window."
                    if brunch_requested and _is_brunch_item(lunch_item)
                    else f"Lunch is scheduled at {lunch_item['start_time']}, outside the 12:00-14:30 window."
                ),
                (
                    "Move brunch into the late morning or early afternoon and keep it close to the first real activity of the day."
                    if brunch_requested and _is_brunch_item(lunch_item)
                    else "Move lunch into the early afternoon and keep it close to the main activity cluster."
                ),
                severity="error",
            )
        )
        bad_patterns.append(
            "unnatural_brunch"
            if brunch_requested and _is_brunch_item(lunch_item)
            else "late_lunch" if lunch_item["start_minutes"] > 14 * 60 + 30 else "unnatural_lunch"
        )
    elif lunch_item is None:
        issue_details.append(
            _issue(
                "missing_lunch",
                "No clear brunch/lunch stop is scheduled." if brunch_requested else "No clear lunch stop is scheduled.",
                (
                    "Insert one brunch or lunch stop around 10:30-13:30 so the day feels sustainable."
                    if brunch_requested
                    else "Insert one lunch stop around 12:00-14:30 so the day feels sustainable."
                ),
                severity="warning",
            )
        )

    if dinner_item is not None and not dinner_ok:
        issue_details.append(
            _issue(
                "dinner_timing_bad",
                f"Dinner is scheduled at {dinner_item['start_time']}, outside the 18:30-21:00 window.",
                "Move dinner later in the evening and place it near the closing experience of the day.",
                severity="error",
            )
        )
        bad_patterns.append("unnatural_dinner")
    elif dinner_item is None:
        issue_details.append(
            _issue(
                "missing_dinner",
                "No clear dinner stop is scheduled.",
                "Add a single dinner stop near the end of the day's theme rather than several meal-like filler blocks.",
                severity="warning",
            )
        )

    if art_day_required and art_count < 1:
        issue_details.append(
            _issue(
                "art_focus_missing",
                "An art or museum-focused request produced a day without an art/culture stop.",
                "Insert at least one museum or gallery as a main activity for this day.",
                severity="error",
            )
        )
        bad_patterns.append("art_focus_missing")

    if museum_limit is not None and museum_like_count > museum_limit:
        issue_details.append(
            _issue(
                "museum_density_violation",
                f"Day has {museum_like_count} museum/gallery stops; keep museum-heavy stops at or below {museum_limit} per day.",
                "Trim extra museum stops and replace them with a walk, cafe, or neighborhood block so the day can breathe.",
                severity="error",
                target=str(museum_limit),
            )
        )
        bad_patterns.append("museum_density_violation")

    if family_unsuitable_titles:
        issue_details.append(
            _issue(
                "family_unsuitable_stop",
                f"Family-oriented pacing is broken by nightlife or late-day stops that do not fit children well: {', '.join(family_unsuitable_titles)}.",
                "Swap nightlife or overly late stops for a park, easier walk, or earlier dinner-friendly alternative.",
                severity="error",
                target=", ".join(family_unsuitable_titles),
            )
        )
        bad_patterns.append("family_unsuitable_stop")

    if present_excluded:
        issue_details.append(
            _issue(
                "excluded_category_present",
                f"Excluded categories are present: {', '.join(present_excluded)}.",
                "Remove the excluded category and replace it with a compatible alternative.",
                severity="error",
            )
        )

    if touristiness_mismatch:
        issue_details.append(
            _issue(
                "touristiness_mismatch",
                f"A local or less-touristy request still leans too heavily on iconic sightseeing blocks: {', '.join(tourist_heavy_titles[:3]) or 'tourist-heavy mix'}.",
                "Replace one or more iconic-heavy stops with a neighborhood, park, cafe, or quieter local block.",
                severity="error",
                target=", ".join(tourist_heavy_titles[:3]) or "tourist-heavy mix",
            )
        )
        bad_patterns.append("touristiness_mismatch")

    if meal_dominant and experience_stop_count < 2:
        issue_details.append(
            _issue(
                "meal_heavy_day",
                "The day is dominated by cafe/restaurant-style stops instead of experiences.",
                "Trim meal-like filler stops and insert a stronger main activity, walk, or landmark block.",
                severity="error",
            )
        )
        bad_patterns.append("meal_heavy_day")

    if fatigue_break_missing:
        issue_details.append(
            _issue(
                "fatigue_without_break",
                "A high-effort cultural or sightseeing block is followed by another heavy stop without a recovery beat.",
                "Place a meal, cafe, park, or walking block after the heaviest stop before another major activity.",
                severity="error",
            )
        )
        bad_patterns.append("fatigue_without_break")

    if overloaded_night_tail:
        issue_details.append(
            _issue(
                "night_overload",
                "The day ends with a heavy museum, shopping, or hard sightseeing block instead of a softer evening close.",
                "Move the heavy stop earlier and finish with dinner, a walk, night view, or another low-pressure evening scene.",
                severity="error",
            )
        )
        bad_patterns.append("night_overload")

    if not theme or _looks_generic_theme(theme):
        issue_details.append(
            _issue(
                "theme_missing",
                "The day theme is missing or too generic to explain the day in one sentence.",
                "Regenerate the day theme around the day's main activity, neighborhood, and dining rhythm.",
                severity="error",
            )
        )
        bad_patterns.append("theme_missing")

    if generic_description_count >= 2 or duplicate_description_ratio >= 0.5:
        issue_details.append(
            _issue(
                "generic_description_repetition",
                "Place descriptions repeat generic phrasing too often.",
                "Rewrite descriptions to explain why each stop fits the time slot and the day's theme.",
                severity="warning" if generic_description_count < 3 else "error",
            )
        )
        bad_patterns.append("generic_description_repetition")

    if role_variety < 3:
        issue_details.append(
            _issue(
                "experience_monotony",
                "The day has too little role diversity across experiences.",
                "Mix main activity, meal, walk, and one lighter support block instead of repeating the same role.",
                severity="warning" if main_activity_count else "error",
            )
        )
        bad_patterns.append("experience_monotony")

    score_breakdown = {
        "user_intent_match": _user_intent_match_score(
            items,
            brief,
            art_required=art_day_required,
            family_requested=family_requested,
            local_requested=local_requested,
            tourist_avoid_requested=tourist_avoid_requested,
        ),
        "category_diversity": _category_diversity_score(distinct_categories, repeated_category_count),
        "meal_timing_quality": _meal_timing_score(lunch_item, lunch_ok, dinner_item, dinner_ok),
        "theme_coherence": _theme_coherence_score(theme, items),
        "route_efficiency": _route_efficiency_score(items),
        "experience_value": _experience_value_score(items, meal_dominant=meal_dominant),
        "description_quality": _description_quality_score(items, generic_description_count, duplicate_description_ratio),
    }
    day_score = round(sum(score_breakdown.values()), 2)
    quality_checks = {
        "max_cafes_ok": cafe_count <= 2,
        "cafe_chain_ok": consecutive_cafe_count < 2,
        "restaurant_chain_ok": not consecutive_restaurant_chain,
        "meal_timing_ok": (lunch_item is None or lunch_ok) and (dinner_item is None or dinner_ok),
        "theme_exists": bool(theme) and not _looks_generic_theme(theme),
        "category_diversity_ok": distinct_categories >= 3,
        "matches_user_intent": (not art_day_required) or art_count >= 1,
        "main_activity_exists": main_activity_count >= 1,
        "art_day_ok": (not art_day_required) or art_count >= 1,
        "pace_density_ok": pace_min <= len(items) <= pace_max,
        "recovery_rhythm_ok": not fatigue_break_missing,
        "night_tail_ok": not overloaded_night_tail,
        "family_friendly_ok": (not family_requested) or not family_unsuitable_titles,
        "museum_density_ok": museum_limit is None or museum_like_count <= museum_limit,
        "local_style_ok": not (local_requested or tourist_avoid_requested) or not touristiness_mismatch,
    }

    return {
        "day_number": int(day.get("day_number") or 0),
        "theme": theme,
        "passed": not any(issue.get("severity") == "error" for issue in issue_details) and day_score >= 80.0,
        "score": day_score,
        "errors": [issue["message"] for issue in issue_details if issue.get("severity") == "error"],
        "warnings": [issue["message"] for issue in issue_details if issue.get("severity") == "warning"],
        "repair_suggestions": list(dict.fromkeys(issue["repair"] for issue in issue_details if str(issue.get("repair") or "").strip())),
        "quality_checks": quality_checks,
        "score_breakdown": score_breakdown,
        "bad_patterns": bad_patterns,
        "stats": {
            "item_count": len(items),
            "cafe_count": cafe_count,
            "main_activity_count": main_activity_count,
            "experience_stop_count": experience_stop_count,
            "distinct_categories": distinct_categories,
            "art_stop_count": art_count,
            "local_support_count": local_support_count,
            "tourist_heavy_count": len(tourist_heavy_titles),
            "pace_target_min": pace_min,
            "pace_target_max": pace_max,
        },
        "issue_details": issue_details,
    }


def _issue(
    code: str,
    message: str,
    repair: str,
    *,
    severity: str,
    target: str | None = None,
) -> dict[str, Any]:
    issue = {
        "code": code,
        "message": message,
        "repair": repair,
        "severity": severity,
    }
    if target:
        issue["target"] = target
    return issue


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    place = item.get("place") or {}
    category = str(place.get("category") or "").strip().lower()
    role = str(item.get("role") or place.get("role") or "").strip().lower()
    time_slot = str(item.get("time_slot") or "").strip().lower()
    start_time = str(item.get("start_time") or "").strip()

    if not role:
        if category in ART_CATEGORIES:
            role = "museum_or_gallery"
        elif category in CAFE_CATEGORIES:
            role = "cafe_break"
        elif category in {"restaurant", "bistro", "brasserie"}:
            role = "dinner" if time_slot == "evening" else "lunch"
        elif category in {"bar", "wine_bar"}:
            role = "night_activity"
        elif category in {"park", "neighborhood"}:
            role = "walking_route"
        elif category == "shopping":
            role = "shopping"
        elif category in {"landmark", "cathedral"}:
            role = "landmark"
        else:
            role = "main_activity"

    start_minutes = _parse_minutes(start_time)
    is_meal = bool(item.get("isMeal")) or role in {"lunch", "dinner", "dessert"}
    if not is_meal and category in {"restaurant", "bistro", "brasserie"}:
        is_meal = True
        role = "dinner" if start_minutes >= 17 * 60 else "lunch"
    if not is_meal and category in {"cafe", "bakery"} and time_slot == "lunch":
        is_meal = True
        role = "lunch"
    if not is_meal and category in {"bar", "wine_bar"} and start_minutes >= 18 * 60:
        role = "night_activity"

    is_cafe = bool(place.get("is_cafe")) or category in CAFE_CATEGORIES or role in {"cafe_break", "dessert"}
    is_art_or_culture = bool(place.get("is_art_or_culture")) or category in ART_CATEGORIES or role == "museum_or_gallery"
    is_main_activity = bool(place.get("is_main_activity")) or role in {"main_activity", "museum_or_gallery", "landmark", "shopping"} or category in MAIN_ACTIVITY_CATEGORIES
    neighborhood = str(place.get("neighborhood") or item.get("area") or "").strip() or None

    return {
        "title": str(item.get("title") or place.get("name") or "").strip(),
        "category": category,
        "role": role,
        "description": str(item.get("description") or "").strip(),
        "start_time": start_time,
        "start_minutes": start_minutes,
        "is_meal": is_meal,
        "is_cafe": is_cafe,
        "is_art_or_culture": is_art_or_culture,
        "is_main_activity": is_main_activity,
        "is_night_view_spot": bool(item.get("isNightViewSpot")),
        "lat": _safe_float((place.get("coordinates") or {}).get("lat") or place.get("lat")),
        "lng": _safe_float((place.get("coordinates") or {}).get("lng") or place.get("lng")),
        "neighborhood": neighborhood,
    }


def _is_restaurant_like_item(item: dict[str, Any]) -> bool:
    return item["category"] in RESTAURANT_CATEGORIES or item["role"] in {"lunch", "dinner", "night_activity"}


def _has_consecutive_restaurant_chain(
    items: list[dict[str, Any]],
    *,
    nightlife_requested: bool,
) -> bool:
    previous_restaurant_like: dict[str, Any] | None = None
    for item in items:
        if not _is_restaurant_like_item(item):
            previous_restaurant_like = None
            continue
        if previous_restaurant_like is not None:
            previous_role = previous_restaurant_like["role"]
            current_role = item["role"]
            if nightlife_requested and previous_role == "dinner" and current_role == "night_activity":
                previous_restaurant_like = item
                continue
            if previous_role == "lunch" and current_role == "dinner":
                gap_minutes = item["start_minutes"] - previous_restaurant_like["start_minutes"]
                if gap_minutes >= 4 * 60:
                    previous_restaurant_like = item
                    continue
            return True
        previous_restaurant_like = item
    return False


def _is_high_intensity_item(item: dict[str, Any]) -> bool:
    return item["category"] in HIGH_INTENSITY_CATEGORIES or (
        item["is_main_activity"] and item["role"] not in LOW_INTENSITY_ROLES
    )


def _counts_as_main_activity(item: dict[str, Any], *, local_requested: bool) -> bool:
    if item["is_main_activity"]:
        return True
    return local_requested and item["category"] in {"neighborhood", "park"} and item["role"] == "walking_route"


def _is_brunch_item(item: dict[str, Any]) -> bool:
    text = " ".join(
        [
            str(item.get("title") or ""),
            str(item.get("description") or ""),
            str(item.get("role") or ""),
            str(item.get("category") or ""),
        ]
    ).lower()
    if any(token in text for token in ("brunch", "breakfast", "브런치", "아침식사", "늦은 아침", "늦은아침")):
        return True
    return item["category"] in CAFE_CATEGORIES and item["role"] == "lunch" and _within_window(item["start_minutes"], 9 * 60 + 30, 12 * 60 + 30)


def _pace_bounds(brief: dict[str, Any], items: list[dict[str, Any]]) -> tuple[int, int, str]:
    pace = str(brief.get("pace") or "normal").lower()
    night_tail = any(item["role"] in {"night_activity", "walking_route"} or item["is_meal"] for item in items[-2:])
    if pace == "slow":
        return 3, 6 if night_tail else 5, "relaxed"
    if pace in {"fast", "packed"}:
        return 7, 9, "packed"
    return 5, 7, "normal"


def _max_consecutive_true(items: list[dict[str, Any]], predicate: Any) -> int:
    best = 0
    current = 0
    for item in items:
        if predicate(item):
            current += 1
        else:
            current = 0
        best = max(best, current)
    return best


def _has_fatigue_break_issue(items: list[dict[str, Any]]) -> bool:
    for index, (current, next_item) in enumerate(zip(items, items[1:])):
        if current["is_art_or_culture"] and _is_high_intensity_item(next_item) and next_item["role"] not in LOW_INTENSITY_ROLES:
            return True
        if not (_is_high_intensity_item(current) and _is_high_intensity_item(next_item)):
            continue
        if index + 2 >= len(items):
            continue
        if _is_high_intensity_item(items[index + 2]):
            return True
    return False


def _night_tail_is_overloaded(items: list[dict[str, Any]]) -> bool:
    if not items:
        return False
    tail = items[-1]
    if tail["is_night_view_spot"]:
        return False
    if tail["role"] in {"walking_route", "dinner", "night_activity"} or tail["is_meal"]:
        return False
    return tail["category"] in {"museum", "gallery", "shopping"} or (
        tail["is_main_activity"] and not tail["is_cafe"] and not tail["is_meal"]
    )


def _user_intent_match_score(
    items: list[dict[str, Any]],
    brief: dict[str, Any],
    *,
    art_required: bool,
    family_requested: bool,
    local_requested: bool,
    tourist_avoid_requested: bool,
) -> float:
    if not items:
        return 0.0
    main_activity_count = sum(1 for item in items if _counts_as_main_activity(item, local_requested=local_requested))
    art_count = sum(1 for item in items if item["is_art_or_culture"])
    tourist_heavy_count = sum(1 for item in items if item["category"] in TOURIST_HEAVY_CATEGORIES)
    local_support_count = sum(
        1
        for item in items
        if item["category"] in LOCAL_SUPPORT_CATEGORIES or item["role"] == "walking_route"
    )
    themes = {str(value).lower() for value in brief.get("travel_style") or []}
    score = 15.0
    if main_activity_count >= 1:
        score += 6.0
    if art_required:
        score += 4.0 if art_count >= 1 else -12.0
    if "shopping" in themes and any(item["role"] == "shopping" for item in items):
        score += 2.0
    if {"foodie", "restaurant", "cafe"}.intersection(themes) and any(item["is_meal"] for item in items):
        score += 2.0
    if family_requested:
        score += 2.0 if not _family_unsuitable_titles(items) else -8.0
    if local_requested:
        score += 2.0 if local_support_count >= 2 else -5.0
    if tourist_avoid_requested:
        score += 2.0 if tourist_heavy_count <= max(2, len(items) // 2) else -6.0
    return round(max(0.0, min(QUALITY_WEIGHTS["user_intent_match"], score)), 2)


def _category_diversity_score(distinct_categories: int, repeated_category_count: int) -> float:
    base = {1: 0.0, 2: 6.0, 3: 14.0, 4: 17.0}.get(distinct_categories, 20.0)
    if repeated_category_count > 2:
        base -= 6.0
    return round(max(0.0, min(QUALITY_WEIGHTS["category_diversity"], base)), 2)


def _meal_timing_score(
    lunch_item: dict[str, Any] | None,
    lunch_ok: bool,
    dinner_item: dict[str, Any] | None,
    dinner_ok: bool,
) -> float:
    score = 15.0
    if lunch_item is None:
        score -= 4.0
    elif not lunch_ok:
        score -= 8.0
    if dinner_item is None:
        score -= 4.0
    elif not dinner_ok:
        score -= 8.0
    return round(max(0.0, min(QUALITY_WEIGHTS["meal_timing_quality"], score)), 2)


def _theme_coherence_score(theme: str, items: list[dict[str, Any]]) -> float:
    if not theme:
        return 0.0
    score = 15.0
    if _looks_generic_theme(theme):
        score -= 8.0
    roles = {item["role"] for item in items if item["role"]}
    theme_norm = _normalize(theme)
    local_theme = any(token in theme_norm for token in ("local", "동네", "골목", "산책"))
    if "art" in theme_norm and "museum_or_gallery" not in roles:
        score -= 5.0
    if "shopping" in theme_norm and "shopping" not in roles:
        score -= 4.0
    if ("walk" in theme_norm or "산책" in theme) and "walking_route" not in roles:
        score -= 3.0
    if not any(_counts_as_main_activity(item, local_requested=local_theme) for item in items):
        score -= 4.0
    return round(max(0.0, min(QUALITY_WEIGHTS["theme_coherence"], score)), 2)


def _route_efficiency_score(items: list[dict[str, Any]]) -> float:
    coordinates = [(item["lat"], item["lng"]) for item in items if item["lat"] is not None and item["lng"] is not None]
    if len(coordinates) < 2:
        return 6.0
    distances = []
    for (lat1, lng1), (lat2, lng2) in zip(coordinates, coordinates[1:]):
        distances.append(_distance_km(lat1, lng1, lat2, lng2))
    average_distance = sum(distances) / len(distances)
    if average_distance <= 2.2:
        return 10.0
    if average_distance <= 3.5:
        return 8.0
    if average_distance <= 5.0:
        return 5.0
    return 2.0


def _experience_value_score(items: list[dict[str, Any]], *, meal_dominant: bool) -> float:
    if not items:
        return 0.0
    roles = {item["role"] for item in items if item["role"]}
    localish = any(item["category"] in {"neighborhood", "park"} for item in items)
    main_count = sum(1 for item in items if _counts_as_main_activity(item, local_requested=localish))
    score = 4.0
    if main_count >= 1:
        score += 3.5
    if len(roles) >= 4:
        score += 2.5
    elif len(roles) >= 3:
        score += 1.5
    if meal_dominant:
        score -= 4.0
    return round(max(0.0, min(QUALITY_WEIGHTS["experience_value"], score)), 2)


def _description_quality_score(
    items: list[dict[str, Any]],
    generic_description_count: int,
    duplicate_description_ratio: float,
) -> float:
    if not items:
        return 0.0
    score = 5.0
    score -= min(3.0, generic_description_count * 1.2)
    score -= 2.0 if duplicate_description_ratio >= 0.5 else 0.0
    return round(max(0.0, min(QUALITY_WEIGHTS["description_quality"], score)), 2)


def _aggregate_breakdown(day_reports: list[dict[str, Any]]) -> dict[str, float]:
    if not day_reports:
        return {key: 0.0 for key in QUALITY_WEIGHTS}
    totals = {key: 0.0 for key in QUALITY_WEIGHTS}
    for report in day_reports:
        for key, value in (report.get("score_breakdown") or {}).items():
            totals[key] += float(value or 0)
    return {key: round(totals[key] / len(day_reports), 2) for key in QUALITY_WEIGHTS}


def _art_trip_requested(brief: dict[str, Any], prompt: str) -> bool:
    tokens = " ".join(
        [
            str(prompt or ""),
            *[str(value) for value in brief.get("travel_style") or []],
            *[str(value) for value in brief.get("meal_preference") or []],
            str(brief.get("source_text") or ""),
        ]
    ).lower()
    compact = re.sub(r"[^0-9a-zA-Z가-힣]+", "", tokens)
    if any(token in compact for token in ("박물관보다", "박물관보단", "미술관보다", "미술관보단", "museum보다", "gallery보다")):
        return any(token in tokens for token in ("museum", "gallery", "미술관", "예술", "아트")) and any(
            str(value).lower() in {"museum", "art", "culture"} for value in brief.get("travel_style") or []
        )
    return any(token in tokens for token in ("museum", "art trip", "museum trip", "gallery", "미술관", "예술", "아트", "박물관"))


def _theme_requests_art(theme: str) -> bool:
    compact = _normalize(theme)
    if not compact:
        return False
    return any(
        token in compact
        for token in (
            "art",
            "museum",
            "gallery",
            "culture",
            "미술관",
            "박물관",
            "예술",
            "아트",
            "루브르",
            "오르세",
        )
    )


def _family_trip_requested(brief: dict[str, Any], prompt: str) -> bool:
    tokens = " ".join(
        [
            str(prompt or ""),
            str(brief.get("source_text") or ""),
            *[str(value) for value in brief.get("travel_style") or []],
        ]
    ).lower()
    return any(token in tokens for token in ("family", "가족", "아이", "kids", "children"))


def _local_mood_requested(brief: dict[str, Any], prompt: str) -> bool:
    tokens = " ".join(
        [
            str(prompt or ""),
            str(brief.get("source_text") or ""),
            *[str(value) for value in brief.get("travel_style") or []],
        ]
    ).lower()
    return any(token in tokens for token in ("local", "로컬", "현지인", "골목", "숨은", "quiet", "조용"))


def _brunch_requested(brief: dict[str, Any], prompt: str) -> bool:
    tokens = " ".join(
        [
            str(prompt or ""),
            str(brief.get("source_text") or ""),
            *[str(value) for value in brief.get("meal_preference") or []],
        ]
    ).lower()
    return any(token in tokens for token in ("brunch", "breakfast", "브런치", "늦은 아침", "늦은아침"))


def _tourist_avoid_requested(brief: dict[str, Any], prompt: str) -> bool:
    tokens = " ".join(
        [
            str(prompt or ""),
            str(brief.get("source_text") or ""),
            *[str(value) for value in brief.get("must_avoid") or []],
        ]
    ).lower()
    return any(token in tokens for token in ("touristy", "less touristy", "관광지 최소", "너무 관광", "덜 관광", "quiet"))


def _nightlife_requested(brief: dict[str, Any], prompt: str) -> bool:
    tokens = " ".join(
        [
            str(prompt or ""),
            str(brief.get("source_text") or ""),
            *[str(value) for value in brief.get("travel_style") or []],
            *[str(value) for value in brief.get("meal_preference") or []],
        ]
    ).lower()
    return any(token in tokens for token in ("jazz", "재즈", "nightlife", "bar", "wine", "칵테일", "와인바"))


def _museum_limit_per_day(brief: dict[str, Any]) -> int | None:
    value = brief.get("museum_limit_per_day")
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return None
    return limit if limit > 0 else None


def _family_unsuitable_titles(items: list[dict[str, Any]]) -> list[str]:
    titles: list[str] = []
    for item in items:
        if item["category"] in FAMILY_UNFRIENDLY_CATEGORIES or item["role"] == "night_activity":
            titles.append(item["title"])
            continue
        if (
            item["start_minutes"] >= 20 * 60 + 30
            and not item["is_night_view_spot"]
            and item["role"] not in {"dinner", "walking_route"}
        ):
            titles.append(item["title"])
    return list(dict.fromkeys(title for title in titles if title))


def _has_touristiness_mismatch(
    items: list[dict[str, Any]],
    *,
    local_requested: bool,
    tourist_avoid_requested: bool,
) -> bool:
    if not items or not (local_requested or tourist_avoid_requested):
        return False
    tourist_heavy_count = sum(1 for item in items if item["category"] in TOURIST_HEAVY_CATEGORIES)
    local_support_count = sum(
        1
        for item in items
        if item["category"] in LOCAL_SUPPORT_CATEGORIES or item["role"] == "walking_route"
    )
    consecutive_tourist_heavy = _max_consecutive_true(items, lambda item: item["category"] in TOURIST_HEAVY_CATEGORIES)
    threshold = max(3, math.ceil(len(items) * (0.5 if local_requested else 0.6)))
    return tourist_heavy_count >= threshold and (
        local_support_count <= 1 or consecutive_tourist_heavy >= 3
    )


def _requested_trip_concepts(brief: dict[str, Any], prompt: str) -> set[str]:
    concepts: set[str] = set()
    tokens = {
        _normalize(value)
        for value in [
            prompt,
            brief.get("source_text"),
            *(brief.get("travel_style") or []),
            *(brief.get("meal_preference") or []),
        ]
        if str(value or "").strip()
    }
    joined = " ".join(
        [
            str(prompt or "").lower(),
            str(brief.get("source_text") or "").lower(),
            *[str(value).lower() for value in brief.get("travel_style") or [] if str(value).strip()],
            *[str(value).lower() for value in brief.get("meal_preference") or [] if str(value).strip()],
        ]
    )

    def has_any(*values: str) -> bool:
        return any(_normalize(value) in tokens or value.lower() in joined for value in values)

    if has_any("romance", "romantic", "데이트", "기념일", "couple", "커플"):
        concepts.add("romantic")
    if has_any("landmark", "classic", "관광지", "명소", "architecture", "history"):
        concepts.add("landmark")
    if has_any("museum", "gallery", "art", "culture", "미술관", "박물관", "예술", "아트"):
        concepts.add("art")
    if has_any("shopping", "쇼핑"):
        concepts.add("shopping")
    if has_any("local", "로컬", "현지", "동네", "골목", "숨은", "quiet", "조용"):
        concepts.add("local")
    if has_any("night_view", "nightview", "야경", "노을", "sunset", "반짝"):
        concepts.add("night_view")
    if has_any("foodie", "맛집", "미식", "restaurant", "식당", "레스토랑", "french", "bistro", "brasserie"):
        concepts.add("foodie")
    if has_any("cafe", "coffee", "bakery", "dessert", "카페", "커피", "디저트", "베이커리"):
        concepts.add("cafe")
    if has_any("family", "가족", "아이", "kids", "children"):
        concepts.add("family")
    return concepts.intersection(CORE_TRIP_CONCEPTS)


def _item_concepts(item: dict[str, Any]) -> set[str]:
    concepts: set[str] = set()
    category = item["category"]
    role = item["role"]
    text = " ".join([item["title"], item["description"], category, role]).lower()
    compact = _normalize(text)

    if item["is_art_or_culture"] or category in ART_CATEGORIES:
        concepts.add("art")
    if category in {"landmark", "cathedral", "museum", "gallery"} or role == "landmark":
        concepts.add("landmark")
    if role == "shopping" or category == "shopping":
        concepts.add("shopping")
    if category in LOCAL_SUPPORT_CATEGORIES or role == "walking_route":
        concepts.add("local")
    if item["is_meal"] or category in RESTAURANT_CATEGORIES:
        concepts.add("foodie")
    if item["is_cafe"] or category in CAFE_CATEGORIES:
        concepts.add("cafe")
    if item["is_night_view_spot"] or (item["start_minutes"] >= 18 * 60 and category in {"landmark", "cathedral"}):
        concepts.update({"night_view", "romantic"})
    if item["start_minutes"] >= 18 * 60 and (role in {"dinner", "walking_route"} or category in {"park", "neighborhood", "landmark"}):
        concepts.add("romantic")
    if "romantic" in compact or "데이트" in text or "기념일" in text:
        concepts.add("romantic")
    if category in LOCAL_SUPPORT_CATEGORIES and item["start_minutes"] < 20 * 60:
        concepts.add("family")
    return concepts


def _matched_trip_concepts(itinerary_days: list[dict[str, Any]], requested_concepts: set[str]) -> tuple[set[str], list[str]]:
    trip_day_count = max(len(itinerary_days), 1)
    normalized_items = [
        _normalize_item(item)
        for day in itinerary_days
        for item in day.get("items") or []
        if item.get("itemKind") != "gap"
    ]
    matched: set[str] = set()
    local_support_count = sum(
        1 for item in normalized_items if item["category"] in LOCAL_SUPPORT_CATEGORIES or item["role"] == "walking_route"
    )
    family_unsuitable = _family_unsuitable_titles(normalized_items)
    shopping_count = sum(1 for item in normalized_items if item["role"] == "shopping" or item["category"] == "shopping")
    cafe_count = sum(1 for item in normalized_items if item["is_cafe"])
    meal_count = sum(1 for item in normalized_items if item["is_meal"])
    art_count = sum(1 for item in normalized_items if item["is_art_or_culture"])
    landmark_count = sum(1 for item in normalized_items if item["category"] in TOURIST_HEAVY_CATEGORIES or item["role"] == "landmark")
    night_view_count = sum(1 for item in normalized_items if item["is_night_view_spot"] or (item["start_minutes"] >= 18 * 60 and item["category"] in {"landmark", "cathedral"}))
    romantic_support_count = sum(1 for item in normalized_items if "romantic" in _item_concepts(item))

    if "local" in requested_concepts and local_support_count >= 2:
        matched.add("local")
    if "family" in requested_concepts and not family_unsuitable and local_support_count >= 1:
        matched.add("family")
    if "shopping" in requested_concepts and shopping_count >= 1:
        matched.add("shopping")
    if "cafe" in requested_concepts and cafe_count >= 1:
        matched.add("cafe")
    if "foodie" in requested_concepts and meal_count >= 2:
        matched.add("foodie")
    if "art" in requested_concepts and art_count >= _minimum_trip_concept_count("art", trip_day_count):
        matched.add("art")
    if "landmark" in requested_concepts and landmark_count >= 2:
        matched.add("landmark")
    if "night_view" in requested_concepts and night_view_count >= 1:
        matched.add("night_view")
    if "romantic" in requested_concepts and romantic_support_count >= 2 and meal_count >= 1:
        matched.add("romantic")

    missing = [concept for concept in sorted(requested_concepts) if concept not in matched]
    return matched, missing


def _minimum_trip_concept_count(concept: str, trip_day_count: int) -> int:
    if concept == "art":
        return 2 if trip_day_count >= 3 else 1
    return 1


def _trip_concept_coverage_is_weak(requested_concepts: set[str], matched_concepts: set[str]) -> bool:
    primary_requested = requested_concepts.intersection(CORE_TRIP_CONCEPTS)
    if not primary_requested:
        return False
    if len(primary_requested) == 1:
        return not bool(matched_concepts.intersection(primary_requested))
    required = min(2, len(primary_requested))
    return len(matched_concepts.intersection(primary_requested)) < required


def _excluded_categories(brief: dict[str, Any], prompt: str) -> set[str]:
    source = " ".join(
        [
            str(prompt or ""),
            str(brief.get("source_text") or ""),
            *[str(value) for value in brief.get("must_avoid") or []],
        ]
    ).lower()
    excluded = {
        category
        for category, phrases in CATEGORY_EXCLUSION_HINTS.items()
        if any(phrase.lower() in source for phrase in phrases)
    }
    raw_must_avoid = {str(value).lower().strip() for value in brief.get("must_avoid") or [] if str(value).strip()}
    excluded.update({value for value in raw_must_avoid if value in {"cafe", "restaurant", "shopping", "museum"}})
    return excluded


def _max_consecutive_category_count(categories: list[str]) -> int:
    best = 0
    current = 0
    previous = ""
    for category in categories:
        if category == previous:
            current += 1
        else:
            current = 1
            previous = category
        best = max(best, current)
    return best


def _generic_description_count(items: list[dict[str, Any]]) -> int:
    count = 0
    for item in items:
        description = str(item.get("description") or "").lower()
        if any(phrase in description for phrase in GENERIC_DESCRIPTION_PHRASES):
            count += 1
    return count


def _duplicate_description_ratio(items: list[dict[str, Any]]) -> float:
    descriptions = [_normalize(item.get("description") or "") for item in items if str(item.get("description") or "").strip()]
    if len(descriptions) < 2:
        return 0.0
    unique_count = len(set(descriptions))
    return round(1.0 - (unique_count / max(len(descriptions), 1)), 2)


def _counts_as_experience_stop(item: dict[str, Any]) -> bool:
    return not item["is_meal"] and not item["is_cafe"]


def _looks_generic_theme(theme: str) -> bool:
    compact = _normalize(theme)
    if not compact:
        return True
    return any(_normalize(phrase) in compact for phrase in GENERIC_THEME_PHRASES)


def _theme_signature(theme: str) -> str:
    compact = _normalize(theme)
    compact = re.sub(r"day[0-9]+", "", compact)
    compact = re.sub(r"[0-9]+일차", "", compact)
    return compact[:40]


def _parse_minutes(value: str) -> int:
    try:
        hour, minute = str(value or "").split(":", 1)
        return (int(hour) * 60) + int(minute)
    except (TypeError, ValueError):
        return 15 * 60


def _within_window(value: int, minimum: int, maximum: int) -> bool:
    return minimum <= value <= maximum


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize(value: Any) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", str(value or "").lower())


def _distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371.0
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    )
    return radius * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))
