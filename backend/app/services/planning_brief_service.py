from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from app.services.user_intent_service import analyze_user_intent
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
    {"샹젤리제", "샹젤리제거리", "champselysees", "champselyseesavenue"},
    {"센강", "seine", "seineriver"},
    {"몽마르트르", "몽마르트", "사크레쾨르", "사크레쾨르성당", "sacrecoeur", "sacrecoeurbasilica", "montmartre"},
    {"노트르담", "notredame", "notredamecathedral"},
    {"생트샤펠", "생트샤펠성당", "saintechapelle", "saintechapel", "saintchapelle"},
    {"마레", "마레지구", "lemarais", "marais"},
    {"생제르맹", "생제르맹데프레", "saintgermain", "saintgermaindespres", "saint-germain", "saint-germain-des-pres"},
    {"튈르리", "튈르리가든", "tuileries", "tuileriesgarden"},
    {"뤽상부르", "뤽상부르공원", "룩셈부르크", "룩셈부르크공원", "luxembourg", "luxembourggardens"},
    {"팔레가르니에", "가르니에", "palaisgarnier", "opera"},
    {"팔레루아얄", "팔레 루아얄", "palaisroyal", "palais-royal"},
    {"재즈바", "재즈", "jazzbar", "jazz", "caveaudelahuchette", "huchette", "위셰트"},
)

PLACE_CANONICALS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("에펠탑", ("에펠탑", "에펠", "eiffel tower", "eiffel", "tour eiffel")),
    ("루브르 박물관", ("루브르 박물관", "루브르", "louvre museum", "louvre")),
    ("오르세 미술관", ("오르세 미술관", "오르세", "orsay", "musee d'orsay", "musée d'orsay")),
    ("개선문", ("개선문", "arc de triomphe", "arc")),
    ("샹젤리제 거리", ("샹젤리제 거리", "샹젤리제", "champs elysees", "champs-élysées")),
    ("몽마르트르", ("몽마르트르", "몽마르트", "사크레쾨르", "사크레 쾨르", "sacre coeur", "sacré-cœur", "sacre-coeur", "montmartre")),
    ("마레 지구", ("마레 지구", "마레", "le marais", "marais")),
    ("센강 산책", ("센강", "세느강", "seine river", "seine")),
    ("노트르담 대성당", ("노트르담 대성당", "노트르담", "notre dame")),
    ("생트샤펠", ("생트샤펠", "생트 샤펠", "sainte chapelle", "sainte-chapelle", "saint chapelle")),
    ("튈르리 정원", ("튈르리 정원", "튈르리", "tuileries")),
    ("생제르맹 데 프레", ("생제르맹 데 프레", "생제르맹데프레", "생제르맹", "saint germain", "saint-germain", "saint germain des pres", "saint-germain-des-pres", "saintgermaindespres")),
    ("뤽상부르 공원", ("뤽상부르 공원", "뤽상부르", "룩셈부르크 공원", "룩셈부르크", "luxembourg gardens", "luxembourg")),
    ("오페라 가르니에", ("오페라 가르니에", "오페라", "가르니에", "팔레 가르니에", "palais garnier", "palais-garnier", "opera garnier", "opera")),
    ("팔레 루아얄", ("팔레 루아얄", "팔레루아얄", "palais royal", "palais-royal", "palaisroyal")),
    ("르 카보 드 라 위셰트", ("르 카보 드 라 위셰트", "재즈바", "재즈 바", "jazz bar", "jazz", "caveau de la huchette", "huchette")),
)

PLANNER_SELF_CORRECTION_MARKER = "[Planner self-correction context]"

INCLUDE_CUES = (
    "꼭",
    "반드시",
    "무조건",
    "포함",
    "넣",
    "가고싶",
    "보고싶",
    "방문",
    "핵심",
    "보고싶",
    "보고싶어",
    "보고 싶",
    "보고",
    "가고 싶",
    "산책",
    "마무리",
    "시작",
    "go",
    "visit",
    "must",
    "include",
)

AVOID_CUES = (
    "빼",
    "제외",
    "말고",
    "대신",
    "보다",
    "없는",
    "없이",
    "가지않",
    "가지 않",
    "안가",
    "안 가",
    "넣지",
    "피하",
    "싫",
    "avoid",
    "without",
    "skip",
    "exclude",
    "don't",
    "dont",
)


def extract_user_request_text(value: Any) -> str:
    text = str(value or "")
    if PLANNER_SELF_CORRECTION_MARKER in text:
        text = text.split(PLANNER_SELF_CORRECTION_MARKER, 1)[0]
    return text.strip()


def build_planning_brief(
    *,
    plan: dict[str, Any] | None = None,
    request: Any | None = None,
    trip: dict[str, Any] | None = None,
    intent: str = "create_trip",
    strict_constraints: bool = False,
    language: str = "ko",
) -> dict[str, Any]:
    plan = deepcopy(plan or {})
    trip = deepcopy(trip or {})
    preferences = plan.get("preferences") if isinstance(plan.get("preferences"), dict) else {}
    dates = plan.get("dates") if isinstance(plan.get("dates"), dict) else {}
    pace = plan.get("pace") if isinstance(plan.get("pace"), dict) else {}
    mobility = plan.get("mobility") if isinstance(plan.get("mobility"), dict) else {}
    budget = plan.get("budget") if isinstance(plan.get("budget"), dict) else {}
    lodging = plan.get("lodging") if isinstance(plan.get("lodging"), dict) else {}
    constraints = plan.get("constraints") if isinstance(plan.get("constraints"), dict) else {}

    request_tags = list(getattr(request, "style_tags", []) or [])
    trip_tags = list(trip.get("style_tags") or [])
    source_text = " ".join(
        text
        for text in [
            extract_user_request_text(plan.get("_source_message")),
            extract_user_request_text(getattr(request, "prompt", "")),
            extract_user_request_text(trip.get("prompt")),
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
    must_include, must_avoid = _resolve_place_preference_conflicts(must_include, must_avoid)
    agent_constraints = _derive_agent_constraint_harness(
        source_text=source_text,
        must_include=must_include,
        must_avoid=must_avoid,
    )
    must_include, must_avoid = _apply_place_constraints_to_preferences(
        must_include,
        must_avoid,
        list(agent_constraints.get("place_constraints") or []),
    )
    night_view_required = bool(preferences.get("night_view_required")) or "night_view" in travel_style or _has_night_view_signal(source_text)
    low_walking_requested = _has_family_or_low_walking_signal(source_text, request_tags, trip_tags)
    pace_level = str(pace.get("level") or _pace_from_tags(travel_style) or "normal").lower()
    if pace_level == "normal" and _has_slow_signal(source_text):
        pace_level = "slow"
    if pace_level == "normal" and low_walking_requested:
        pace_level = "slow"
    if pace_level == "normal" and _has_fast_signal(source_text):
        pace_level = "fast"
    transport_preference = str(mobility.get("travel_mode") or "both").lower()
    if low_walking_requested and transport_preference in {"both", "walk", "walking", "on_foot", "on-foot"}:
        transport_preference = "transit"
    mobility_constraints = dict(mobility) if isinstance(mobility, dict) else {}
    if low_walking_requested:
        current_walk_km = _safe_float(mobility_constraints.get("max_walk_km_per_day"), 5)
        current_segment = _safe_int(mobility_constraints.get("max_walk_segment_minutes"), 20)
        current_scenic = _safe_int(mobility_constraints.get("max_scenic_walk_minutes"), 55)
        mobility_constraints.update(
            {
                "walking_intensity": "low",
                "max_walk_km_per_day": min(current_walk_km, 5),
                "max_walk_segment_minutes": min(current_segment, 20),
                "max_scenic_walk_minutes": min(current_scenic, 55),
                "prefer_transit_between_areas": True,
            }
        )
    start_time, end_time = _slot_window(preferred_time_slots)
    budget_mode = budget.get("budget_mode") or ("save" if _has_budget_save_signal(source_text) else "normal")
    museum_limit_per_day = constraints.get("museum_per_day") or _museum_limit_from_source_text(source_text)

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
    if low_walking_requested:
        hard_constraints.append(
            ConstraintSpec(
                id="low_walking_required",
                type="mobility",
                value={"walking_intensity": "low", "max_scenic_walk_minutes": 55},
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
            "budget_mode": budget_mode,
        },
        hotel_area_preference=str(lodging.get("text") or "").strip() or None,
        transport_preference=transport_preference,
        walking_intensity="low" if low_walking_requested else str(mobility_constraints.get("walking_intensity") or "").strip() or None,
        mobility_constraints=mobility_constraints,
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
        source_text=source_text,
    )
    brief = payload.model_dump(mode="json")
    user_intent_analysis = analyze_user_intent(
        prompt=source_text,
        style_tags=_merge_unique(request_tags, trip_tags, travel_style),
        language=language,
    )
    brief["user_intent_analysis"] = user_intent_analysis
    brief["place_constraints"] = list(agent_constraints.get("place_constraints") or [])
    brief["ordered_anchors"] = list(agent_constraints.get("ordered_anchors") or [])
    if museum_limit_per_day:
        brief["museum_limit_per_day"] = int(museum_limit_per_day)
        brief["soft_constraints"].append(
            ConstraintSpec(
                id="museum_limit_per_day",
                type="museum_limit_per_day",
                value=int(museum_limit_per_day),
                priority="soft",
                source="user",
            ).model_dump(mode="json")
        )
    if agent_constraints.get("final_anchor"):
        brief["final_anchor"] = agent_constraints["final_anchor"]
    if user_intent_analysis.get("raw_constraints"):
        brief["raw_constraints"] = list(user_intent_analysis.get("raw_constraints") or [])
    if user_intent_analysis.get("uncertainties"):
        brief["uncertainties"] = list(user_intent_analysis.get("uncertainties") or [])
    return brief


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
    identity_catalog = [_item_identity_text(item) for item in real_items]

    must_include = [str(value) for value in brief.get("must_include") or [] if str(value).strip()]
    must_avoid = [str(value) for value in brief.get("must_avoid") or [] if str(value).strip()]
    preferred_slots = {str(value) for value in brief.get("preferred_time_slots") or [] if str(value)}
    meal_preferences = [str(value).lower() for value in brief.get("meal_preference") or [] if str(value).strip()]
    pace = str(brief.get("pace") or "normal").lower()
    travel_style = {str(value).lower() for value in brief.get("travel_style") or [] if str(value).strip()}

    missing_must_include = [value for value in must_include if not _constraint_matches_catalog(value, identity_catalog)]
    included_must_avoid = [value for value in must_avoid if _constraint_matches_catalog(value, identity_catalog)]

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
    has_brunch = False
    has_jazz_bar = False
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
        has_time_locked_anchor = any(
            str(item.get("slotLockReason") or "")
            in {
                "structured_place_constraint",
                "structured_final_anchor",
                "scoped_daypart",
                "agent_replanner_time_slot",
                "agent_replanner_final_anchor",
                "final_night_anchor",
            }
            for item in day_items
        )
        if helper_gap_minutes >= 90 and not has_time_locked_anchor:
            quality_violations.append(f"day_{day.get('day_number')}_helper_block_ratio")
        real_meal_items = [item for item in day_items if _is_meal_item(item)]
        day_has_brunch = any(
            (
                str(item.get("time_slot") or "") in {"morning", "lunch"}
                or (_item_start_minutes(item) is not None and int(_item_start_minutes(item) or 0) < 13 * 60)
            )
            and any(
                token in _normalize_name(
                    " ".join(
                        [
                            str((item.get("place") or {}).get("name") or ""),
                            str((item.get("place") or {}).get("category") or ""),
                            " ".join(str(value) for value in ((item.get("place") or {}).get("cuisine") or []) if value),
                            str(item.get("description") or ""),
                        ]
                    )
                )
                for token in ("brunch", "breakfast", "cafe", "bakery", "브런치", "카페")
            )
            for item in day_items
        )
        if day_has_brunch:
            has_brunch = True
        day_has_cafe_dessert_anchor = any(
            str(((item.get("place") or {}).get("category")) or "").lower() in {"cafe", "bakery"}
            or any(
                token in _normalize_name(
                    " ".join(
                        [
                            str((item.get("place") or {}).get("name") or ""),
                            " ".join(str(value) for value in ((item.get("place") or {}).get("tags") or []) if value),
                            " ".join(str(value) for value in ((item.get("place") or {}).get("cuisine") or []) if value),
                        ]
                    )
                )
                for token in ("cafe", "coffee", "dessert", "cake", "bakery", "patisserie", "croissant")
            )
            for item in day_items
        )
        if day_has_cafe_dessert_anchor:
            has_cafe_dessert_anchor = True
        day_has_french_dinner = any(
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
        )
        if day_has_french_dinner:
            has_french_dinner = True
        day_has_jazz_bar = any(
            str(item.get("time_slot") or "") in {"evening", "night"}
            and (
                str(((item.get("place") or {}).get("category")) or "").lower() == "bar"
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
                    for token in ("jazz", "재즈", "bar", "wine")
                )
            )
            for item in day_items
        )
        if day_has_jazz_bar:
            has_jazz_bar = True
        day_has_night_climax = day_items and (
            bool(day_items[-1].get("isNightViewSpot"))
            or _is_named_night_climax(day_items[-1])
            or (
                str(day_items[-1].get("time_slot") or "") in {"evening", "night"}
                and (
                    str(((day_items[-1].get("place") or {}).get("category")) or "").lower() in {"bar", "wine_bar"}
                    or any(
                        token
                        in _normalize_name(
                            " ".join(
                                [
                                    str((day_items[-1].get("place") or {}).get("name") or ""),
                                    " ".join(str(value) for value in ((day_items[-1].get("place") or {}).get("tags") or []) if value),
                                    " ".join(str(value) for value in ((day_items[-1].get("place") or {}).get("cuisine") or []) if value),
                                ]
                            )
                        )
                        for token in ("jazz", "재즈", "wine", "bar")
                    )
                )
            )
        )
        if day_has_night_climax:
            has_night_climax = True
        if pace == "slow":
            max_places = 5
            main_activity_count = sum(
                1
                for item in day_items
                if str(item.get("role") or ((item.get("place") or {}).get("role") or "")).lower() in {"main_activity", "museum_or_gallery", "landmark", "shopping"}
                or str(((item.get("place") or {}).get("category")) or "").lower() in {"museum", "gallery", "landmark", "cathedral", "shopping"}
            )
            romantic_landmark_day = any(token in travel_style for token in {"romance", "romantic", "couple"}) and any(
                token in travel_style for token in {"landmark", "classic"}
            )
            day_has_walk_reset = any(
                str(item.get("role") or ((item.get("place") or {}).get("role") or "")).lower() == "walking_route"
                or str(((item.get("place") or {}).get("category")) or "").lower() in {"park", "neighborhood"}
                for item in day_items
            )
            if romantic_landmark_day and day_has_night_climax and real_meal_items and main_activity_count >= 2:
                max_places = 6
            elif day_has_night_climax and (day_has_cafe_dessert_anchor or day_has_french_dinner):
                max_places = 6
            elif real_meal_items and main_activity_count <= 2 and (day_has_cafe_dessert_anchor or day_has_walk_reset):
                max_places = 6
            if len(day_items) > max_places:
                pace_violations.append(f"day_{day.get('day_number')}_too_many_places")
            if high_burden_count > 1:
                pace_violations.append(f"day_{day.get('day_number')}_high_transfer")
        if helper_item_count > 2:
            quality_violations.append(f"day_{day.get('day_number')}_helper_block_count")
        if helper_gap_minutes > 90:
            if has_time_locked_anchor:
                warnings.append(f"day_{day.get('day_number')}_long_helper_time")
            else:
                quality_violations.append(f"day_{day.get('day_number')}_helper_block_minutes")
        elif helper_gap_minutes > 45:
            warnings.append(f"day_{day.get('day_number')}_long_helper_time")
        if longest_helper_block >= 120:
            if has_time_locked_anchor:
                warnings.append(f"day_{day.get('day_number')}_single_helper_block")
            else:
                quality_violations.append(f"day_{day.get('day_number')}_single_helper_block")

    if brief.get("night_view_required") and not has_night_climax:
        quality_violations.append("night_climax_missing")

    if any(token in travel_style for token in {"cafe", "dessert", "foodie"}) and not has_cafe_dessert_anchor:
        meal_preference_violations.append("cafe_dessert_underrepresented")

    if any("french" in preference for preference in meal_preferences) and not has_french_dinner:
        meal_preference_violations.append("french_dinner_underrepresented")

    if any("brunch" in preference for preference in meal_preferences) and not has_brunch:
        meal_preference_violations.append("brunch_underrepresented")

    if any(preference in {"jazz", "jazz_bar", "bar", "wine"} for preference in meal_preferences) and not has_jazz_bar:
        meal_preference_violations.append("late_bar_underrepresented")

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
    helper_penalty = 0.0 if not quality_violations else min(0.35, round(helper_ratio * 0.75, 3))
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
        str(brief.get("source_text") or ""),
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
    return any(token in title for token in ("점심", "저녁", "lunch", "dinner"))


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
    compact_source = source_text.replace(" ", "")
    next_must_include = list(must_include)
    next_must_avoid = list(must_avoid)
    next_preferred_time_slots = list(preferred_time_slots)
    next_meal_preference = list(meal_preference)
    next_travel_style = list(travel_style)

    text_include, text_avoid = _extract_place_preferences_from_text(source_text)
    if _has_museum_avoid_signal(source_text):
        text_avoid = _merge_unique(text_avoid, ["루브르 박물관", "오르세 미술관"])
    if _has_orsay_only_signal(source_text):
        text_include = _merge_unique(text_include, ["오르세 미술관"])
        text_avoid = _merge_unique(text_avoid, ["루브르 박물관"])
    if _has_generic_museum_include_signal(source_text):
        text_include = _merge_unique(text_include, ["오르세 미술관"])
    if _has_generic_park_signal(source_text):
        text_include = _merge_unique(text_include, ["뤽상부르 공원"])
        next_travel_style = _merge_unique(next_travel_style, ["nature", "park", "walk"])
    if _has_cathedral_course_signal(source_text):
        text_include = _merge_unique(text_include, ["\ub178\ud2b8\ub974\ub2f4 \ub300\uc131\ub2f9", "\uc0dd\ud2b8\uc0e4\ud3a0"])
        next_travel_style = _merge_unique(next_travel_style, ["architecture", "walk"])
    if _has_cathedral_avoid_signal(source_text):
        text_avoid = _merge_unique(text_avoid, ["노트르담 대성당", "생트샤펠"])
    if _has_negative_jazz_or_nightlife_signal(source_text):
        text_avoid = _merge_unique(text_avoid, ["르 카보 드 라 위셰트"])
    if _has_famous_landmark_signal(source_text):
        next_travel_style = _merge_unique(next_travel_style, ["landmark", "classic"])
    if _has_landmark_minimize_signal(source_text):
        next_travel_style = _merge_unique(next_travel_style, ["local"])
    if _has_generic_river_walk_signal(source_text):
        text_include = _merge_unique(text_include, ["센강 산책"])
    if _has_positive_river_signal(source_text):
        text_include = _merge_unique(text_include, ["\uc13c\uac15 \uc0b0\ucc45"])
        text_avoid = _remove_place_aliases(text_avoid, ["\uc13c\uac15 \uc0b0\ucc45"])
    if _has_diversity_signal(source_text):
        text_include = _merge_unique(text_include, ["센강 산책", "뤽상부르 공원"])
        next_travel_style = _merge_unique(next_travel_style, ["walk", "scenic", "nature"])
    if text_include:
        next_must_avoid = _remove_place_aliases(next_must_avoid, text_include)
    if text_avoid:
        next_must_include = _remove_place_aliases(next_must_include, text_avoid)
    next_must_include = _merge_unique(next_must_include, text_include)
    next_must_avoid = _merge_unique(next_must_avoid, text_avoid)

    eiffel_requested = ("에펠" in source_text or "eiffel" in lowered) and not any(
        _has_avoid_cue_near_alias(source_text, alias) for alias in ("에펠", "에펠탑", "eiffel")
    )
    if not next_must_include and eiffel_requested:
        next_must_include = _merge_unique(next_must_include, ["에펠탑"])
    elif eiffel_requested and _has_night_view_signal(source_text):
        next_must_include = _merge_unique(next_must_include, ["에펠탑"])
    if _has_budget_save_signal(source_text):
        next_travel_style = _merge_unique(next_travel_style, ["budget", "walk"])
    if _has_early_start_signal(source_text):
        next_preferred_time_slots = _merge_unique(next_preferred_time_slots, ["morning"])
    if _has_late_start_signal(source_text):
        next_preferred_time_slots = _merge_unique(next_preferred_time_slots, ["afternoon"])
    elif "오후" in source_text:
        next_preferred_time_slots = _merge_unique(next_preferred_time_slots, ["afternoon"])
    if _has_night_view_signal(source_text):
        next_travel_style = _merge_unique(next_travel_style, ["night_view"])
        next_preferred_time_slots = _merge_unique(next_preferred_time_slots, ["evening", "night"])
    if (
        any(token in lowered for token in ("museum", "gallery", "art", "culture", "미술관", "박물관", "갤러리", "예술", "아트", "전시"))
        and not _has_museum_deprioritize_signal(source_text)
    ):
        next_travel_style = _merge_unique(next_travel_style, ["museum", "art", "culture"])
        if not any(str(value).strip() for value in next_must_include):
            next_must_include = _merge_unique(next_must_include, ["오르세 미술관"])
    if any(token in lowered for token in ("sunset", "석양", "선셋")):
        next_preferred_time_slots = _merge_unique(next_preferred_time_slots, ["evening"])
    if any(token in lowered for token in ("brunch", "브런치", "늦은 아침", "늦은아침")):
        next_meal_preference = _merge_unique(next_meal_preference, ["brunch"])
        next_travel_style = _merge_unique(next_travel_style, ["foodie"])
        next_preferred_time_slots = _merge_unique(next_preferred_time_slots, ["lunch"])
    if any(token in lowered for token in ("dinner", "디너", "저녁 식사", "저녁은", "프렌치 디너")):
        next_preferred_time_slots = _merge_unique(next_preferred_time_slots, ["evening"])
    if any(token in lowered for token in ("cafe", "coffee", "카페")):
        next_meal_preference = _merge_unique(next_meal_preference, ["cafe"])
        next_travel_style = _merge_unique(next_travel_style, ["cafe", "foodie"])
    if any(token in lowered for token in ("dessert", "bakery", "디저트", "베이커리")):
        next_meal_preference = _merge_unique(next_meal_preference, ["dessert"])
        next_travel_style = _merge_unique(next_travel_style, ["dessert", "foodie"])
    if any(token in lowered for token in ("french", "프렌치", "브라세리", "비스트로")):
        next_meal_preference = _merge_unique(next_meal_preference, ["french", "bistro"])
        next_preferred_time_slots = _merge_unique(next_preferred_time_slots, ["evening"])
    if _has_vegetarian_signal(source_text):
        next_meal_preference = _merge_unique(next_meal_preference, ["vegetarian"])
    if any(token in lowered or token in compact_source for token in ("meal", "restaurant", "\uc2dd\uc0ac\uc7a5\uc18c", "\uc2dd\uc0ac", "\ubc25")):
        next_meal_preference = _merge_unique(next_meal_preference, ["meal_preference"])
    jazz_avoided = _has_negative_jazz_or_nightlife_signal(source_text) or any(
        _has_avoid_cue_near_alias(source_text, token) for token in ("jazz", "재즈", "재즈바", "jazz bar")
    )
    if any(token in lowered for token in ("jazz", "재즈", "재즈바", "jazz bar")) and not jazz_avoided:
        next_meal_preference = _merge_unique(next_meal_preference, ["jazz_bar"])
        next_travel_style = _merge_unique(next_travel_style, ["jazz", "nightlife"])
        next_preferred_time_slots = _merge_unique(next_preferred_time_slots, ["evening", "night"])
    elif jazz_avoided:
        next_meal_preference = [value for value in next_meal_preference if str(value).lower() not in {"jazz", "jazz_bar", "bar", "wine"}]
        next_travel_style = [value for value in next_travel_style if str(value).lower() not in {"jazz", "nightlife"}]
    if any(token in lowered for token in ("local", "로컬", "골목", "마레", "생제르맹", "saint-germain", "saint germain")):
        next_travel_style = _merge_unique(next_travel_style, ["local"])
    if any(token in lowered for token in ("photo", "사진", "포토", "인생샷")):
        next_travel_style = _merge_unique(next_travel_style, ["photo"])
    if any(token in lowered or token in compact_source for token in ("indoor", "실내", "비오는", "비 오는", "우천", "rain", "rainy")):
        next_travel_style = _merge_unique(next_travel_style, ["indoor"])
    if any(token in lowered or token in compact_source for token in ("bar", "wine bar", "와인바", "바 분위기", "바분위기", "칵테일", "cocktail")):
        next_meal_preference = _merge_unique(next_meal_preference, ["bar"])
        next_travel_style = _merge_unique(next_travel_style, ["nightlife"])
        next_preferred_time_slots = _merge_unique(next_preferred_time_slots, ["evening", "night"])
    if _has_slow_signal(source_text):
        next_travel_style = _merge_unique(next_travel_style, ["slow"])
    next_must_include, next_must_avoid = _resolve_place_preference_conflicts(next_must_include, next_must_avoid)
    return next_must_include, next_must_avoid, next_preferred_time_slots, next_meal_preference, next_travel_style


def _extract_place_preferences_from_text(source_text: str) -> tuple[list[str], list[str]]:
    compact = source_text.replace(" ", "")
    segments = [segment for segment in re.split(r"[.!?\n。！？]+", source_text) if segment.strip()] or [source_text]
    include: list[str] = []
    avoid: list[str] = []

    for canonical, aliases in PLACE_CANONICALS:
        if not _contains_place_alias(source_text, aliases):
            continue
        if any(_has_avoid_cue_near_alias(source_text, alias) for alias in aliases):
            avoid.append(canonical)
            continue
        if any(_has_photo_only_marker_near_alias(source_text, alias) for alias in aliases):
            include.append(canonical)
            continue
        if any(_has_only_marker_near_alias(source_text, alias) for alias in aliases):
            include.append(canonical)
            continue
        if any(_has_include_cue_near_alias(source_text, alias) for alias in aliases):
            include.append(canonical)
            continue
        for segment in segments:
            if not _contains_place_alias(segment, aliases):
                continue
            alias_index = _first_alias_index(segment, aliases)
            scope_end = _next_place_alias_index_after(segment, alias_index)
            avoid_index = _first_cue_index_between(segment, AVOID_CUES, alias_index, scope_end)
            normalized_segment = _normalize_name(segment)
            upper_bound = scope_end if scope_end >= 0 else len(normalized_segment)
            include_index = _first_applicable_include_cue_index(normalized_segment[alias_index:upper_bound])
            if include_index >= 0:
                include_index += alias_index
            scoped_segment = normalized_segment[alias_index : scope_end if scope_end >= 0 else None]
            if avoid_index >= 0 and _avoid_cue_belongs_to_category_subject(normalized_segment[alias_index:avoid_index]):
                avoid_index = -1
            if any(
                token in scoped_segment
                for token in (
                    "\ubb34\ub9ac\uc5c6\uc774",
                    "\ubb34\ub9ac\uc5c6\ub294",
                    "\ubd80\ub2f4\uc5c6\uc774",
                    "\ubd80\ub2f4\uc5c6\ub294",
                    "\uc790\uc5f0\uc2a4\ub7fd\uac8c",
                    "\uc790\uc5f0\uc2a4\ub7ec\uc6b4",
                )
            ):
                avoid_index = -1
            if (
                alias_index >= 0
                and avoid_index >= 0
                and avoid_index - alias_index <= 18
                and not (include_index >= 0 and include_index < avoid_index)
            ):
                avoid.append(canonical)
                break
            if any(cue.replace(" ", "") in segment.replace(" ", "").lower() for cue in INCLUDE_CUES):
                cue_index = include_index
                if alias_index >= 0 and cue_index >= 0 and (avoid_index < 0 or cue_index < avoid_index):
                    include.append(canonical)
                    break
        else:
            if canonical == "센강 산책" and _has_night_view_signal(source_text):
                include.append(canonical)
            elif canonical == "몽마르트르" and any(token in compact for token in ("몽마르트", "사크레쾨르")):
                include.append(canonical)
            else:
                include.append(canonical)

    return _merge_unique(include), _merge_unique(avoid)


def _derive_agent_constraint_harness(
    *,
    source_text: str,
    must_include: list[str],
    must_avoid: list[str],
) -> dict[str, Any]:
    place_constraints: list[dict[str, Any]] = []
    include_aliases = _preference_aliases(must_include)
    avoid_aliases = _preference_aliases(must_avoid)
    for canonical, aliases in PLACE_CANONICALS:
        if not _contains_place_alias(source_text, aliases):
            continue
        canonical_aliases = _constraint_aliases(canonical)
        if canonical == "르 카보 드 라 위셰트" and _has_negative_jazz_or_nightlife_signal(source_text):
            intent = "avoid"
        else:
            intent = _scoped_place_intent(source_text, aliases)
        if intent is None:
            if canonical_aliases & avoid_aliases:
                intent = "avoid"
            elif canonical_aliases & include_aliases:
                intent = "include"
            else:
                intent = "include"
        slot = _scoped_slot_for_alias(source_text, aliases)
        is_final = _scoped_final_for_alias(source_text, aliases)
        constraint = {
            "target": canonical,
            "canonical": _canonical_place_key(canonical),
            "intent": intent,
            "source": "parser_context",
        }
        if slot:
            constraint["time_slot"] = slot
        if is_final:
            constraint["final"] = True
        place_constraints.append(constraint)

    ordered_anchors = _derive_ordered_anchors(source_text, place_constraints)
    final_anchor = next(
        (str(constraint.get("target")) for constraint in place_constraints if constraint.get("final") and constraint.get("intent") != "avoid"),
        None,
    )
    if not final_anchor and ordered_anchors and _last_order_anchor_is_final_like(source_text, place_constraints, ordered_anchors):
        final_anchor = ordered_anchors[-1]
        for constraint in place_constraints:
            if str(constraint.get("target") or "") == final_anchor:
                constraint["final"] = True
                break
    if not final_anchor and _seine_after_dinner_is_final_like(source_text, place_constraints):
        final_anchor = next(
            (str(constraint.get("target")) for constraint in place_constraints if constraint.get("canonical") == "seine"),
            None,
        )
        for constraint in place_constraints:
            if str(constraint.get("target") or "") == final_anchor:
                constraint["final"] = True
                break
    if final_anchor and final_anchor in ordered_anchors:
        ordered_anchors = [anchor for anchor in ordered_anchors if anchor != final_anchor]
        ordered_anchors.append(final_anchor)
    return {
        "place_constraints": _dedupe_place_constraints(place_constraints),
        "ordered_anchors": ordered_anchors,
        "final_anchor": final_anchor,
    }


def _seine_after_dinner_is_final_like(source_text: str, place_constraints: list[dict[str, Any]]) -> bool:
    if not any(constraint.get("canonical") == "seine" and constraint.get("intent") != "avoid" for constraint in place_constraints):
        return False
    normalized = _normalize_name(source_text)
    seine_index = min((index for alias in ("\uc13c\uac15", "seine") if (index := normalized.find(_normalize_name(alias))) >= 0), default=-1)
    if seine_index < 0:
        return False
    dinner_index = min(
        (
            index
            for cue in ("\uc800\ub141", "\ub514\ub108", "\ube44\uc2a4\ud2b8\ub85c", "dinner", "bistro")
            if (index := normalized.find(_normalize_name(cue))) >= 0
        ),
        default=-1,
    )
    if dinner_index < 0 or dinner_index > seine_index:
        return False
    window = normalized[seine_index : seine_index + 16]
    return any(cue in window for cue in ("\uc0b0\ucc45", "\uc57c\uacbd", "\ubc24", "walk", "night"))


def _last_order_anchor_is_final_like(
    source_text: str,
    place_constraints: list[dict[str, Any]],
    ordered_anchors: list[str],
) -> bool:
    normalized = _normalize_name(source_text)
    if not any(token in normalized for token in ("\uc21c\uc11c", "order", "then")):
        return False
    last = ordered_anchors[-1]
    constraint = next((item for item in place_constraints if str(item.get("target") or "") == last), None)
    if not isinstance(constraint, dict):
        return False
    return str(constraint.get("time_slot") or "") in {"evening", "night"}


def _apply_place_constraints_to_preferences(
    must_include: list[str],
    must_avoid: list[str],
    place_constraints: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    next_include = list(must_include)
    next_avoid = list(must_avoid)
    for constraint in place_constraints:
        target = str(constraint.get("target") or "").strip()
        intent = str(constraint.get("intent") or "").strip()
        if not target:
            continue
        if intent == "avoid":
            next_include = _remove_place_aliases(next_include, [target])
            next_avoid = _merge_unique(next_avoid, [target])
        elif intent == "include":
            next_avoid = _remove_place_aliases(next_avoid, [target])
            next_include = _merge_unique(next_include, [target])
    return _resolve_place_preference_conflicts(next_include, next_avoid)


def _preference_aliases(values: list[str]) -> set[str]:
    aliases: set[str] = set()
    for value in values:
        aliases.update(_constraint_aliases(str(value)))
    return aliases


def _scoped_place_intent(source_text: str, aliases: tuple[str, ...]) -> str | None:
    normalized = _normalize_name(source_text)
    for alias in aliases:
        alias_norm = _normalize_name(alias)
        if not alias_norm:
            continue
        start = normalized.find(alias_norm)
        if start < 0:
            continue
        alias_raw = re.escape(str(alias).lower())
        raw_after = source_text.lower()[source_text.lower().find(str(alias).lower()) + len(str(alias)) :][:24]
        if re.match(r"\s*\ub9cc[^,.;!?]{0,14}\ub9d0\uace0", raw_after):
            return "include"
        post_alias = normalized[start + len(alias_norm) : start + len(alias_norm) + 24]
        post_next_alias = _next_alias_offset(post_alias)
        scoped_post_alias = post_alias[:post_next_alias] if post_next_alias >= 0 else post_alias
        after = normalized[start + len(alias_norm) : start + len(alias_norm) + 30]
        next_alias = _next_alias_offset(after)
        scoped_after = after[:next_alias] if next_alias >= 0 else after
        before = normalized[max(0, start - 14) : start]
        if _has_avoid_cue_near_alias(source_text, alias) or _has_scoped_avoid_cue(before, scoped_after):
            return "avoid"
        if _has_include_cue_in_scope(scoped_post_alias):
            return "include"
        include_near_alias = _has_include_cue_near_alias(source_text, alias)
        previous_alias = _previous_place_alias_index_before(source_text, start)
        if include_near_alias and (previous_alias < 0 or previous_alias < max(0, start - 14)):
            return "include"
        if _has_scoped_include_cue(before, scoped_after):
            return "include"
    return None


def _has_scoped_avoid_cue(before: str, after: str) -> bool:
    combined = f"{before}{after}"
    if any(token in combined for token in ("\uc0ac\uc9c4\ub9cc", "\uc0ac\uc9c4\ucc0d", "photo")):
        return False
    if after.startswith("\ub9cc") and "\ub9d0\uace0" in after:
        return False
    if any(
        token in after
        for token in (
            "\ubb34\ub9ac\uc5c6\uc774",
            "\ubb34\ub9ac\uc5c6\ub294",
            "\ubd80\ub2f4\uc5c6\uc774",
            "\ubd80\ub2f4\uc5c6\ub294",
            "\uc790\uc5f0\uc2a4\ub7fd\uac8c",
            "\uc790\uc5f0\uc2a4\ub7ec\uc6b4",
        )
    ):
        return False
    avoid_index = _first_cue_index(after, AVOID_CUES)
    if avoid_index >= 0 and _avoid_cue_belongs_to_category_subject(after[:avoid_index]):
        return False
    return any(_normalize_name(cue) in after for cue in AVOID_CUES) or any(
        _normalize_name(cue) in before for cue in ("avoid", "without", "skip", "exclude")
    )


def _has_scoped_include_cue(before: str, after: str) -> bool:
    return any(_normalize_name(cue) in before for cue in ("\uaf2d", "\ubc18\ub4dc\uc2dc", "must")) or any(
        _include_cue_applies(after, cue) for cue in INCLUDE_CUES
    )


def _scoped_slot_for_alias(source_text: str, aliases: tuple[str, ...]) -> str | None:
    normalized = _normalize_name(source_text)
    slot_cues = {
        "morning": ("\uc624\uc804", "\uc544\uce68", "\uc810\uc2ec\uc804", "morning"),
        "afternoon": ("\uc624\ud6c4", "\uc810\uc2ec\ud6c4", "afternoon"),
        "evening": ("\uc800\ub141", "\ubc24", "\uc57c\uacbd", "\uc11d\uc591", "\ub178\uc744", "evening", "night", "sunset"),
    }
    for alias in aliases:
        explicit_slot = _explicit_slot_pattern_for_alias(source_text, alias)
        if explicit_slot:
            return explicit_slot
        alias_norm = _normalize_name(alias)
        if not alias_norm:
            continue
        start = normalized.find(alias_norm)
        if start < 0:
            continue
        end = start + len(alias_norm)
        previous_alias = _previous_place_alias_index_before(source_text, start)
        next_alias = _next_place_alias_index_after(source_text, start)
        scope_start = max(previous_alias + 1 if previous_alias >= 0 else 0, start - 20)
        scope_end = min(next_alias if next_alias >= 0 else len(normalized), end + 24)
        before = normalized[scope_start:start]
        after = normalized[end:scope_end]
        after_candidates: list[tuple[int, str]] = []
        before_candidates: list[tuple[int, str]] = []
        for slot, cues in slot_cues.items():
            for cue in cues:
                cue_norm = _normalize_name(cue)
                if not cue_norm:
                    continue
                after_index = after.find(cue_norm)
                if 0 <= after_index <= 10 and not _slot_cue_belongs_to_later_meal_subject(
                    after[:after_index],
                    after[after_index : after_index + 14],
                ):
                    after_candidates.append((after_index, slot))
                before_index = before.rfind(cue_norm)
                if before_index >= 0 and not _slot_cue_belongs_to_previous_subject(
                    before[before_index + len(cue_norm) :]
                ):
                    before_candidates.append((len(before) - before_index, slot))
        if after_candidates:
            after_index, after_slot = min(after_candidates, key=lambda item: item[0])
            marker_text = after[:after_index]
            if any(token in marker_text for token in ("\ub05d\ub0b4", "\ud6c4", "\ub2e4\uc74c")):
                pass
            elif any(marker_text.endswith(marker) or marker in marker_text for marker in ("\uc740", "\ub294", "\uc744", "\ub97c", "\uc5d4", "\uc5d0\ub294")):
                return after_slot
        if before_candidates:
            return min(before_candidates, key=lambda item: item[0])[1]
        if after_candidates:
            return min(after_candidates, key=lambda item: item[0])[1]
        if before_candidates:
            return min(before_candidates, key=lambda item: item[0])[1]
    return None


def _explicit_slot_pattern_for_alias(source_text: str, alias: str) -> str | None:
    compact = _normalize_name(source_text)
    alias_norm = _normalize_name(alias)
    if not compact or not alias_norm or alias_norm not in compact:
        return None
    source_raw = source_text.lower()
    alias_raw = re.escape(str(alias).lower())
    if alias_norm in {"\uc13c\uac15", "seine", "seineriver"} and re.search(
        rf"{alias_raw}\s*[,，]?\s*(?:\ubc24|\uc57c\uacbd|\uc7ac\uc988|night|jazz)",
        source_raw,
    ):
        return "evening"
    regex_slot_patterns = {
        "morning": ("\uc624\uc804", "\uc544\uce68", "\uc810\uc2ec\\s*\uc804"),
        "afternoon": ("\uc624\ud6c4", "\uc810\uc2ec\\s*\ud6c4"),
        "evening": ("\uc800\ub141", "\ubc24", "\uc57c\uacbd", "\uc11d\uc591", "\ub178\uc744"),
    }
    for slot, cues in regex_slot_patterns.items():
        for cue in cues:
            if re.search(rf"{alias_raw}\s*(?:\uc740|\ub294|\uc744|\ub97c|\uc5d0|\uc5d4|\uc5d0\ub294)?\s*{cue}", source_raw):
                return slot
    for slot, cues in regex_slot_patterns.items():
        for cue in cues:
            if re.search(rf"{cue}\s*(?:\uc5d0|\uc5d4|\uc5d0\ub294)?\s*{alias_raw}", source_raw):
                return slot
    before_patterns = {
        "morning": ("\uc624\uc804", "\uc544\uce68", "\uc810\uc2ec\uc804"),
        "afternoon": ("\uc624\ud6c4", "\uc810\uc2ec\ud6c4"),
        "evening": ("\uc800\ub141", "\ubc24", "\uc57c\uacbd", "\uc11d\uc591", "\ub178\uc744"),
    }
    before_particles = ("", "\uc5d0", "\uc5d4", "\uc5d0\ub294")
    after_particles = ("", "\uc740", "\ub294", "\uc744", "\ub97c", "\uc5d0", "\uc5d4", "\uc5d0\ub294")
    start = compact.find(alias_norm)
    while start >= 0:
        end = start + len(alias_norm)
        before = compact[max(0, start - 12) : start]
        after = compact[end : end + 14]
        for slot, cues in before_patterns.items():
            for cue in cues:
                cue_norm = _normalize_name(cue)
                if not cue_norm:
                    continue
                for particle in after_particles:
                    if after.startswith(f"{particle}{cue_norm}"):
                        return slot
        for slot, cues in before_patterns.items():
            for cue in cues:
                cue_norm = _normalize_name(cue)
                if not cue_norm:
                    continue
                for particle in before_particles:
                    if before.endswith(f"{cue_norm}{particle}"):
                        return slot
        start = compact.find(alias_norm, end)
    return None


def _scoped_final_for_alias(source_text: str, aliases: tuple[str, ...]) -> bool:
    normalized = _normalize_name(source_text)
    final_cues = ("\ub9c8\uc9c0\ub9c9", "\ub9c8\ubb34\ub9ac", "\ub05d", "final", "finish", "end")
    for alias in aliases:
        alias_norm = _normalize_name(alias)
        if not alias_norm:
            continue
        search_from = 0
        while True:
            start = normalized.find(alias_norm, search_from)
            if start < 0:
                break
            end = start + len(alias_norm)
            previous_alias = _previous_place_alias_index_before(source_text, start)
            next_alias = _next_place_alias_index_after(source_text, start)
            scope_start = max(previous_alias + 1 if previous_alias >= 0 else 0, start - 22)
            scope_end = min(next_alias if next_alias >= 0 else len(normalized), end + 28)
            before = normalized[scope_start:start]
            after = normalized[end:scope_end]
            if "\uc55e\uc5d0\ub294" in before:
                search_from = end
                continue
            if "\ub05d\ub0b4\uace0" in before:
                search_from = end
                continue
            truncated_before_next_alias = False
            if "\uc55e\uc5d0\ub294" in after:
                after = after[: after.find("\uc55e\uc5d0\ub294")]
                truncated_before_next_alias = True
            if after.startswith("\ub97c\ub05d\ub0b4\uace0") or after.startswith("\uc744\ub05d\ub0b4\uace0") or after.startswith("\ub05d\ub0b4\uace0"):
                search_from = end
                continue
            before_has_final = any(
                before.endswith(_normalize_name(cue))
                or before.endswith(f"{_normalize_name(cue)}\uc740")
                or before.endswith(f"{_normalize_name(cue)}\ub294")
                or before.endswith(f"{_normalize_name(cue)}\uc744")
                or before.endswith(f"{_normalize_name(cue)}\ub97c")
                for cue in final_cues
                if _normalize_name(cue)
            ) or before.endswith("\ub9c8\uc9c0\ub9c9anchor\ub294") or before.endswith("\ub9c8\uc9c0\ub9c9\uc575\ucee4\ub294")
            after_has_final = any(_normalize_name(cue) in after for cue in final_cues)
            if after_has_final:
                cue_positions = [after.find(_normalize_name(cue)) for cue in final_cues if _normalize_name(cue) in after]
                cue_index = min(cue_positions) if cue_positions else -1
                if cue_index >= 0 and _final_cue_belongs_to_later_activity(after[:cue_index]):
                    after_has_final = False
            if after_has_final and next_alias >= 0 and not truncated_before_next_alias:
                search_from = end
                continue
            if before_has_final or after_has_final:
                return True
            search_from = end
    return False


def _final_cue_belongs_to_later_activity(text_before_final_cue: str) -> bool:
    return any(
        token in text_before_final_cue
        for token in (
            "\uc624\ud6c4",
            "\uce74\ud398",
            "\uc2dd\uc0ac",
            "\uc800\ub141",
            "\ube0c\ub7f0\uce58",
            "\ub514\ub108",
            "\ubc25",
        )
    )


def _derive_ordered_anchors(source_text: str, place_constraints: list[dict[str, Any]]) -> list[str]:
    if not place_constraints:
        return []
    normalized = _normalize_name(source_text)
    has_order_signal = any(
        token in normalized
        for token in (
            "\uc21c\uc11c",
            "\uadf8\ub2e4\uc74c",
            "\ub2e4\uc74c",
            "\uc774\uc5b4",
            "\uc774\uc5b4\uc9c0",
            "\ub9c8\uc9c0\ub9c9",
            "\ub9c8\ubb34\ub9ac",
            "order",
            "then",
        )
    )
    timed = [constraint for constraint in place_constraints if constraint.get("time_slot") or constraint.get("final")]
    if not has_order_signal and len(timed) < 2:
        return []
    positions: list[tuple[int, str]] = []
    for constraint in place_constraints:
        if constraint.get("intent") == "avoid":
            continue
        target = str(constraint.get("target") or "")
        aliases = next((aliases for canonical, aliases in PLACE_CANONICALS if canonical == target), ())
        index = _first_alias_index(source_text, aliases) if aliases else -1
        if index >= 0:
            positions.append((index, target))
    return list(dict.fromkeys(target for _, target in sorted(positions)))


def _dedupe_place_constraints(place_constraints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for constraint in place_constraints:
        target = str(constraint.get("target") or "")
        if not target or target in seen:
            continue
        seen.add(target)
        deduped.append(constraint)
    return deduped


def _canonical_place_key(target: str) -> str | None:
    normalized = _normalize_name(target)
    mapping = {
        "eiffel": ("에펠", "eiffel"),
        "louvre": ("루브르", "louvre"),
        "orsay": ("오르세", "orsay"),
        "seine": ("센강", "세느", "seine"),
        "notre": ("노트르담", "notre"),
        "sainte": ("생트샤펠", "sainte", "chapelle"),
        "marais": ("마레", "marais"),
        "saint_germain": ("생제르맹", "saintgermain", "saint-germain"),
        "montmartre": ("몽마르트", "montmartre"),
        "arc": ("개선문", "arc"),
        "champs": ("샹젤리제", "champs"),
        "luxembourg": ("뤽상부르", "룩셈부르크", "luxembourg"),
        "tuileries": ("튈르리", "tuileries"),
        "garnier": ("가르니에", "오페라", "garnier", "opera"),
        "palais_royal": ("팔레루아얄", "palaisroyal"),
        "jazz": ("재즈", "jazz", "huchette", "르카보", "카보드라위셰트", "위셰트"),
    }
    for key, aliases in mapping.items():
        if any(_normalize_name(alias) in normalized for alias in aliases):
            return key
    return None


def _contains_place_alias(text: str, aliases: tuple[str, ...]) -> bool:
    normalized_text = _normalize_name(text)
    lowered = text.lower()
    return any(_normalize_name(alias) in normalized_text or alias.lower() in lowered for alias in aliases)


def _first_alias_index(text: str, aliases: tuple[str, ...]) -> int:
    normalized_text = _normalize_name(text)
    indices = [normalized_text.find(_normalize_name(alias)) for alias in aliases if _normalize_name(alias) in normalized_text]
    return min(indices) if indices else -1


def _first_cue_index(text: str, cues: tuple[str, ...]) -> int:
    normalized_text = _normalize_name(text)
    indices = [normalized_text.find(_normalize_name(cue)) for cue in cues if _normalize_name(cue) in normalized_text]
    return min(indices) if indices else -1


def _first_cue_index_after(text: str, cues: tuple[str, ...], alias_index: int) -> int:
    if alias_index < 0:
        return -1
    normalized_text = _normalize_name(text)
    indices = [
        index
        for cue in cues
        if (normalized_cue := _normalize_name(cue))
        and (index := normalized_text.find(normalized_cue, alias_index)) >= 0
    ]
    return min(indices) if indices else -1


def _first_cue_index_between(text: str, cues: tuple[str, ...], start: int, end: int = -1) -> int:
    if start < 0:
        return -1
    normalized_text = _normalize_name(text)
    upper_bound = end if end >= 0 else len(normalized_text)
    indices = [
        index
        for cue in cues
        if (normalized_cue := _normalize_name(cue))
        and (index := normalized_text.find(normalized_cue, start, upper_bound)) >= 0
    ]
    return min(indices) if indices else -1


def _next_place_alias_index_after(text: str, alias_index: int) -> int:
    if alias_index < 0:
        return -1
    normalized_text = _normalize_name(text)
    offsets = [
        index
        for _, aliases in PLACE_CANONICALS
        for alias in aliases
        if (alias_norm := _normalize_name(alias))
        and (index := normalized_text.find(alias_norm, alias_index + 1)) > alias_index
    ]
    return min(offsets) if offsets else -1


def _previous_place_alias_index_before(text: str, alias_index: int) -> int:
    if alias_index < 0:
        return -1
    normalized_text = _normalize_name(text)
    offsets = [
        index
        for _, aliases in PLACE_CANONICALS
        for alias in aliases
        if (alias_norm := _normalize_name(alias))
        and (index := normalized_text.rfind(alias_norm, 0, alias_index)) >= 0
    ]
    return max(offsets) if offsets else -1


def _has_include_cue_near_alias(text: str, alias: str) -> bool:
    normalized_text = _normalize_name(text)
    normalized_alias = _normalize_name(alias)
    start = normalized_text.find(normalized_alias)
    if start < 0:
        return False
    before = normalized_text[max(0, start - 6) : start]
    after = normalized_text[start + len(normalized_alias) : start + len(normalized_alias) + 28]
    next_alias_offset = _next_alias_offset(after)
    if next_alias_offset >= 0:
        after = after[:next_alias_offset]
    before_strong = any(_normalize_name(cue) in before for cue in ("꼭", "반드시", "무조건", "must"))
    after_include = _has_include_cue_in_scope(after)
    if after_include:
        avoid_index = _first_cue_index(after, AVOID_CUES)
        include_index = _first_applicable_include_cue_index(after)
        return include_index >= 0 and (avoid_index < 0 or include_index < avoid_index)
    return before_strong


def _has_include_cue_in_scope(text: str) -> bool:
    return _first_applicable_include_cue_index(text) >= 0


def _first_applicable_include_cue_index(text: str) -> int:
    indices = [
        index
        for cue in INCLUDE_CUES
        if (index := _include_cue_index(text, cue)) >= 0
    ]
    return min(indices) if indices else -1


def _include_cue_index(text: str, cue: str) -> int:
    cue_norm = _normalize_name(cue)
    if not cue_norm:
        return -1
    start = text.find(cue_norm)
    while start >= 0:
        if _include_cue_applies_at(text, cue_norm, start):
            return start
        start = text.find(cue_norm, start + len(cue_norm))
    return -1


def _include_cue_applies(text: str, cue: str) -> bool:
    return _include_cue_index(text, cue) >= 0


def _include_cue_applies_at(text: str, cue_norm: str, start: int) -> bool:
    if cue_norm == "\ub123" and text[start : start + 2] == "\ub123\uc9c0":
        return False
    after = text[start : start + max(6, len(cue_norm) + 3)]
    return not any(token in after for token in ("\ub123\uc9c0", "\ub9d0\uace0", "\ube7c", "\uc81c\uc678"))


def _has_only_marker_near_alias(text: str, alias: str) -> bool:
    normalized_text = _normalize_name(text)
    normalized_alias = _normalize_name(alias)
    start = normalized_text.find(normalized_alias)
    if start < 0:
        return False
    after = normalized_text[start + len(normalized_alias) : start + len(normalized_alias) + 3]
    return after.startswith("만")


def _has_avoid_cue_near_alias(text: str, alias: str) -> bool:
    normalized_text = _normalize_name(text)
    normalized_alias = _normalize_name(alias)
    start = normalized_text.find(normalized_alias)
    if start < 0:
        return False
    if _has_photo_only_marker_near_alias(text, alias):
        return False
    after = normalized_text[start + len(normalized_alias) : start + len(normalized_alias) + 8]
    longer_after = normalized_text[start + len(normalized_alias) : start + len(normalized_alias) + 22]
    if longer_after.startswith("\ub9cc") and "\ub9d0\uace0" in longer_after:
        return False
    long_avoid_positions = [longer_after.find(_normalize_name(cue)) for cue in AVOID_CUES if _normalize_name(cue) in longer_after]
    long_avoid_index = min(long_avoid_positions) if long_avoid_positions else -1
    next_alias_offset = _next_alias_offset(longer_after)
    if next_alias_offset >= 0 and (long_avoid_index < 0 or next_alias_offset < long_avoid_index):
        if long_avoid_index >= 0 and _avoid_cue_applies_across_alias(longer_after, next_alias_offset, long_avoid_index):
            after = longer_after[: long_avoid_index + 4]
        else:
            after = longer_after[:next_alias_offset]
    before = normalized_text[max(0, start - 12) : start]
    avoid_positions = [after.find(_normalize_name(cue)) for cue in AVOID_CUES if _normalize_name(cue) in after]
    include_positions = [
        index
        for cue in INCLUDE_CUES
        if (index := _include_cue_index(after, cue)) >= 0
    ]
    if avoid_positions:
        avoid_index = min(avoid_positions)
        if _avoid_cue_belongs_to_category_subject(after[:avoid_index]):
            avoid_positions = []
    if any(
        token in after
        for token in (
            "\ubb34\ub9ac\uc5c6\uc774",
            "\ubb34\ub9ac\uc5c6\ub294",
            "\ubd80\ub2f4\uc5c6\uc774",
            "\ubd80\ub2f4\uc5c6\ub294",
            "\uc790\uc5f0\uc2a4\ub7fd\uac8c",
            "\uc790\uc5f0\uc2a4\ub7ec\uc6b4",
        )
    ):
        avoid_positions = []
    direct_after = bool(avoid_positions) and (not include_positions or min(include_positions) > min(avoid_positions))
    english_before = any(_normalize_name(cue) in before for cue in ("avoid", "without", "skip", "exclude"))
    return direct_after or english_before


def _avoid_cue_applies_across_alias(after_alias: str, next_alias_offset: int, avoid_index: int) -> bool:
    if next_alias_offset < 0 or avoid_index < 0 or next_alias_offset > avoid_index:
        return False
    bridge = after_alias[:next_alias_offset]
    avoid_scope = after_alias[:avoid_index]
    adjacent_applies = len(bridge) <= 1
    connector_applies = any(
        token in bridge
        for token in (
            "\ub098",
            "\uc774\ub098",
            "\uac70\ub098",
            "\ub610\ub294",
            "\ubc0f",
            "\ub791",
            "\ud558\uace0",
            "\uc640",
            "\uacfc",
        )
    )
    grouped_applies = any(
        token in avoid_scope
        for token in (
            "\ub458\ub2e4",
            "\ubaa8\ub450",
            "\uc804\ubd80",
            "both",
            "all",
        )
    )
    return adjacent_applies or connector_applies or grouped_applies


def _slot_cue_belongs_to_previous_subject(text_between_cue_and_alias: str) -> bool:
    return any(
        token in text_between_cue_and_alias
        for token in (
            "\uc81c\uc678",
            "\ube7c",
            "\ub9d0\uace0",
            "\ubbf8\uc220\uad00",
            "\ubc15\ubb3c\uad00",
            "\ud6c4",
            "\ub2e4\uc74c",
            "\uadf8\ub2e4\uc74c",
            "\uc774\uc5b4",
        )
    )


def _slot_cue_belongs_to_later_meal_subject(text_before_cue: str, text_from_cue: str) -> bool:
    if not any(token in text_from_cue for token in ("\uc800\ub141", "\ubc24", "evening", "night")):
        return False
    return any(token in text_before_cue for token in ("\uc26c\uace0", "\ub4e4\ub974", "\uc774\ud6c4", "\ub2e4\uc74c")) or any(
        token in text_from_cue
        for token in (
            "\ud504\ub80c\uce58",
            "\ub514\ub108",
            "\ube44\uc2a4\ud2b8\ub85c",
            "\uc800\ub141\uc740",
            "\uc800\ub141\uc2dd\uc0ac",
            "french",
            "dinner",
            "bistro",
        )
    )


def _avoid_cue_belongs_to_category_subject(text_before_avoid: str) -> bool:
    return any(
        token in text_before_avoid
        for token in (
            "\ubc15\ubb3c\uad00",
            "\ubbf8\uc220\uad00",
            "\ubc24\uc77c\uc815",
            "\ubc24\ub2a6\uac8c",
            "\uc57c\uacbd",
            "\uc7ac\uc988\ubc14",
            "\ub108\ubb34\ub9ce\uc774",
            "\ub9ce\uc774",
        )
    )


def _has_photo_only_marker_near_alias(text: str, alias: str) -> bool:
    normalized_text = _normalize_name(text)
    normalized_alias = _normalize_name(alias)
    start = normalized_text.find(normalized_alias)
    if start < 0:
        return False
    after = normalized_text[start + len(normalized_alias) : start + len(normalized_alias) + 14]
    before = normalized_text[max(0, start - 4) : start]
    window = f"{before}{after}"
    return any(token in window for token in ("사진만", "사진찍", "사진", "포토", "photo", "외관만"))


def _has_museum_avoid_signal(source_text: str) -> bool:
    compact = _normalize_name(source_text)
    if any(
        token in compact
        for token in (
            "\ubc15\ubb3c\uad00\ub9d0\uace0",
            "\ubbf8\uc220\uad00\ub9d0\uace0",
            "\ubc15\ubb3c\uad00\uc81c\uc678",
            "\ubbf8\uc220\uad00\uc81c\uc678",
            "\ubc15\ubb3c\uad00\ube7c",
            "\ubbf8\uc220\uad00\ube7c",
            "\ubc15\ubb3c\uad00\uc740\ub458\ub2e4\ube7c",
            "\ubbf8\uc220\uad00\uc740\ub458\ub2e4\ube7c",
            "\ubc15\ubb3c\uad00\ub458\ub2e4\ube7c",
            "\ubbf8\uc220\uad00\ub458\ub2e4\ube7c",
            "\ubc15\ubb3c\uad00\uc740\ub458\ub2e4\uc81c\uc678",
            "\ubbf8\uc220\uad00\uc740\ub458\ub2e4\uc81c\uc678",
            "\ubc15\ubb3c\uad00\uc804\ubd80\ube7c",
            "\ubbf8\uc220\uad00\uc804\ubd80\ube7c",
            "\ubc15\ubb3c\uad00\uc740\ub2e4\ube7c",
            "\ubbf8\uc220\uad00\uc740\ub2e4\ube7c",
            "\ubc15\ubb3c\uad00\uc2eb",
            "\ubbf8\uc220\uad00\uc2eb",
            "\uc2e4\ub0b4\ubc15\ubb3c\uad00\ub9d0\uace0",
            "avoidmuseum",
            "nomuseum",
        )
    ):
        return True
    return any(
        token in compact
        for token in (
            "유료박물관제외",
            "유료박물관빼",
            "박물관제외",
            "박물관빼",
            "박물관은빼",
            "박물관은전부빼",
            "박물관전부빼",
            "박물관은제외",
            "박물관없이",
            "박물관없는",
            "박물관싫",
            "박물관은싫",
            "미술관제외",
            "미술관빼",
            "미술관은빼",
            "미술관은전부빼",
            "미술관전부빼",
            "미술관은제외",
            "미술관없이",
            "미술관없는",
            "미술관싫",
            "미술관은싫",
            "미술관은빼",
            "미술관은전부빼",
            "미술관은전부제외",
        )
    )


def _has_generic_museum_include_signal(source_text: str) -> bool:
    compact = _normalize_name(source_text)
    if _has_museum_avoid_signal(source_text):
        return False
    if _has_museum_deprioritize_signal(source_text):
        return False
    if any(token in compact for token in ("\ub8e8\ube0c\ub974", "\uc624\ub974\uc138", "louvre", "orsay")):
        return False
    if any(token in compact for token in ("\ubbf8\uc220\uad00", "\ubc15\ubb3c\uad00", "\uc2e4\ub0b4", "\uc804\uc2dc", "museum", "gallery", "indoor")):
        return True
    if any(token in compact for token in ("루브르", "오르세")):
        return False
    return any(token in compact for token in ("미술관", "박물관", "전시"))


def _has_museum_deprioritize_signal(source_text: str) -> bool:
    compact = _normalize_name(source_text)
    return any(
        token in compact
        for token in (
            "박물관보다",
            "박물관보단",
            "미술관보다",
            "미술관보단",
            "museum보다",
            "museumover",
            "gallery보다",
        )
    )


def _has_generic_park_signal(source_text: str) -> bool:
    compact = _normalize_name(source_text)
    if any(token in compact for token in ("뤽상부르", "룩셈부르크", "튈르리")):
        return False
    return any(token in compact for token in ("공원", "정원", "garden", "park", "피크닉"))


def _has_cathedral_course_signal(source_text: str) -> bool:
    compact = _normalize_name(source_text)
    if any(token in compact for token in ("\uc131\ub2f9\uc81c\uc678", "\uc131\ub2f9\ube7c", "\uc131\ub2f9\ub9d0\uace0")):
        return False
    return any(token in compact for token in ("\uc131\ub2f9\ucf54\uc2a4", "\uc131\ub2f9\uc0b0\ucc45", "\uc2dc\ud14c\uc12c", "cathedralcourse", "churchcourse"))


def _has_cathedral_avoid_signal(source_text: str) -> bool:
    compact = _normalize_name(source_text)
    return any(
        token in compact
        for token in (
            "성당이나종교건축물은빼",
            "성당이나종교건축물빼",
            "성당이나종교건축물은제외",
            "성당이나종교건축물제외",
            "종교건축물은빼",
            "종교건축물빼",
            "종교건축물은제외",
            "종교건축물제외",
            "성당은빼",
            "성당빼",
            "성당은제외",
            "성당제외",
            "교회는빼",
            "교회빼",
            "religiousarchitecture",
            "avoidchurch",
            "avoidcathedral",
        )
    )


def _has_vegetarian_signal(source_text: str) -> bool:
    compact = _normalize_name(source_text)
    return any(
        token in compact
        for token in (
            "채식",
            "채식위주",
            "비건",
            "vegetarian",
            "vegan",
            "plantbased",
        )
    )


def _has_negative_jazz_or_nightlife_signal(source_text: str) -> bool:
    compact = _normalize_name(source_text)
    return any(
        token in compact
        for token in (
            "재즈바같은밤장소는빼",
            "재즈바같은밤장소빼",
            "재즈바는빼",
            "재즈바빼",
            "재즈는빼",
            "재즈빼",
            "밤장소는빼",
            "밤장소빼",
            "nightlifeavoid",
            "avoidjazzbar",
            "avoidnightlife",
        )
    )


def _has_landmark_minimize_signal(source_text: str) -> bool:
    compact = _normalize_name(source_text)
    return any(
        token in compact
        for token in (
            "유명한랜드마크는최소화",
            "유명한랜드마크최소화",
            "랜드마크는최소화",
            "랜드마크최소화",
            "유명관광지는너무많지않게",
            "유명관광지너무많지않게",
            "유명관광지는많지않게",
            "유명관광지많지않게",
            "유명관광지는적게",
            "유명관광지적게",
            "대표관광지많지않게",
            "대표명소는최소화",
            "관광지는최소화",
            "관광지최소화",
            "덜관광지",
            "lesstouristy",
        )
    )


def _has_famous_landmark_signal(source_text: str) -> bool:
    compact = _normalize_name(source_text)
    if _has_landmark_minimize_signal(source_text):
        return False
    return any(
        token in compact
        for token in (
            "\uc720\uba85\uad00\uad11\uc9c0",
            "\uc720\uba85\ud55c\uad00\uad11\uc9c0",
            "\uad00\uad11\uc9c0\uc911\uc2ec",
            "\uad00\uad11\uc9c0\uc704\uc8fc",
            "\uad00\uad11\uc911\uc2ec",
            "\uad00\uad11\uc704\uc8fc",
            "\uba85\uc18c\uc911\uc2ec",
            "\uba85\uc18c\uc704\uc8fc",
            "\ub300\ud45c\uba85\uc18c",
            "\ub79c\ub4dc\ub9c8\ud06c",
            "\ucc98\uc74c\uac00\ub294\ud30c\ub9ac",
            "\ud30c\ub9ac\ucc98\uc74c",
            "famouslandmark",
            "classicparis",
        )
    )


def _has_generic_river_walk_signal(source_text: str) -> bool:
    compact = _normalize_name(source_text)
    if any(token in compact for token in ("센강", "세느강", "seine")):
        return False
    if any(token in compact for token in ("강변", "강가", "강변산책", "riverwalk", "riverside")):
        return True
    return "산책" in compact and any(token in compact for token in ("전망", "풍경", "석양", "노을", "다양", "섞"))


def _has_positive_river_signal(source_text: str) -> bool:
    compact = _normalize_name(source_text)
    if not any(token in compact for token in ("\uc13c\uac15", "\uc138\ub290\uac15", "seine")):
        return False
    positive = any(
        token in compact
        for token in (
            "\uc13c\uac15\uc0b0\ucc45",
            "\uc13c\uac15\uc704\uc8fc",
            "\uc13c\uac15\uc911\uc2ec",
            "\uc13c\uac15\ub9cc",
            "\uc13c\uac15\uc73c\ub85c",
            "\uc13c\uac15\uc744",
            "\uc13c\uac15\uc774",
            "seinewalk",
            "seineriver",
        )
    )
    if not positive:
        return False
    negative = any(
        token in compact
        for token in (
            "\uc13c\uac15\uc81c\uc678",
            "\uc13c\uac15\ube7c",
            "\uc13c\uac15\ub9d0\uace0",
            "avoidseine",
            "skipseine",
        )
    )
    return not negative


def _has_diversity_signal(source_text: str) -> bool:
    compact = _normalize_name(source_text)
    return any(token in compact for token in ("다양", "섞인", "섞어", "반복하지말고", "반복하지마"))


def _has_orsay_only_signal(source_text: str) -> bool:
    compact = _normalize_name(source_text)
    return "오르세만" in compact or "오르세미술관만" in compact


def _museum_limit_from_source_text(source_text: str) -> int | None:
    compact = _normalize_name(source_text)
    if not any(token in compact for token in ("박물관", "미술관", "museum")):
        return None
    one_tokens = (
        "하나이하",
        "한개이하",
        "1개이하",
        "하나만",
        "한곳만",
        "대표하나",
        "대표한곳",
        "oneonly",
        "atmostone",
        "museumlimitone",
    )
    two_tokens = ("두개이하", "2개이하", "두곳이하", "둘이하", "atmosttwo")
    if any(token in compact for token in one_tokens):
        return 1
    if any(token in compact for token in two_tokens):
        return 2
    return None


def _next_alias_offset(text: str) -> int:
    offsets = [
        text.find(_normalize_name(alias))
        for _, aliases in PLACE_CANONICALS
        for alias in aliases
        if _normalize_name(alias) and _normalize_name(alias) in text
    ]
    return min(offsets) if offsets else -1


def _resolve_place_preference_conflicts(must_include: list[str], must_avoid: list[str]) -> tuple[list[str], list[str]]:
    avoids = _merge_unique(must_avoid)
    avoid_aliases = set().union(*[_constraint_aliases(value) for value in avoids]) if avoids else set()
    filtered_include = [
        value
        for value in _merge_unique(must_include)
        if not (_constraint_aliases(value) & avoid_aliases)
    ]
    return filtered_include, avoids


def _remove_place_aliases(values: list[str], removals: list[str]) -> list[str]:
    removal_aliases = set().union(*[_constraint_aliases(value) for value in removals]) if removals else set()
    return [
        value
        for value in values
        if not (_constraint_aliases(value) & removal_aliases)
    ]


def _has_night_view_signal(source_text: str) -> bool:
    lowered = source_text.lower()
    compact = _normalize_name(source_text)
    has_sunset = any(token in lowered or token in compact for token in ("sunset", "석양", "선셋", "노을", "해질녘"))
    if _has_negative_night_view_signal(source_text) and not has_sunset:
        return False
    return has_sunset or any(
        token in lowered or token in compact
        for token in ("night view", "night_view", "sparkling", "야경", "밤풍경", "반짝")
    )


def _has_negative_night_view_signal(source_text: str) -> bool:
    compact = _normalize_name(source_text)
    lowered = source_text.lower()
    return any(
        token in compact
        for token in (
            "야경은없어도",
            "야경없어도",
            "야경은없",
            "야경없",
            "야경은빼",
            "야경빼",
            "야경은제외",
            "야경제외",
            "야경말고",
            "야경대신",
            "야경은싫",
            "야경싫",
            "야경필요없",
            "밤일정은빼",
            "밤일정빼",
            "밤늦게까지는싫",
            "밤늦게까지싫",
            "야경은욕심내지",
            "야경욕심내지",
        )
    ) or any(
        token in lowered or token in compact
        for token in (
            "no night view",
            "without night view",
            "skip night view",
            "\ubc24\ub2a6\uc9c0\uc54a\uac8c",
            "\uc57c\uacbd\uae4c\uc9c0\ubb34\ub9ac\ud558\uc9c0",
            "\uc774\ub978\ub9c8\ubb34\ub9ac",
        )
    )


def _has_slow_signal(source_text: str) -> bool:
    lowered = source_text.lower()
    compact = source_text.replace(" ", "")
    return any(
        token in lowered or token in compact
        for token in (
            "\uac00\ubccd\uac8c",
            "\uac00\ubcbc\uc6b4",
            "\ucc9c\ucc9c\ud788",
            "\ucda9\ubd84",
            "\uc815\ub3c4\uba74",
            "\ubb34\ub9ac\uc5c6",
            "\ubb34\ub9ac\ud558\uc9c0",
            "\ubb34\ub9ac\ub9d0",
            "\ud558\ub098\ub9cc",
            "\ub9ce\uc774\ub3cc\uc544\ub2e4\ub2c8\uc9c0",
            "\ubc24\ub2a6\uc9c0\uc54a\uac8c",
            "\uc774\ub978\ub9c8\ubb34\ub9ac",
            "slow",
            "relax",
            "relaxed",
            "healing",
            "천천히",
            "여유",
            "느긋",
            "쉬엄쉬엄",
            "많이 돌아다니는 건 싫",
            "많이걷지",
            "많이안걷",
            "너무많이걷지",
            "이동을줄",
            "부담스럽지",
            "빡세지않게",
            "너무빡세지않게",
            "무리하지않게",
            "장소는적게",
            "4곳이하",
            "세곳정도",
            "욕심내지",
            "가볍게",
            "짧게",
            "쉬는날",
            "휴식",
            "만넣어서",
        )
    )


def _has_family_or_low_walking_signal(source_text: str, *tag_groups: list[str]) -> bool:
    lowered = source_text.lower()
    compact = source_text.replace(" ", "")
    tags = " ".join(str(tag).lower() for group in tag_groups for tag in group)
    return any(
        token in lowered or token in compact or token in tags
        for token in (
            "\uac00\uc871",
            "\uc544\uc774",
            "\ubd80\ubaa8",
            "family",
            "kids",
            "\ub9ce\uc774\uac77\uae30\uc2eb",
            "\ub9ce\uc774\uc548\uac77",
            "\ub9ce\uc774\uac77\ub294\uac74\uc2eb",
            "\ub9ce\uc774\uac77\ub294\uac74\uc2eb\uc5b4",
            "\uc624\ub798\uac77\ub294\uac74\ud53c\ud558",
            "\uc801\uac8c\uac77",
            "\ub3c4\ubcf4\ubd80\ub2f4",
            "\uac77\ub294\uac70\uc2eb",
            "\uc774\ub3d9\uac15\ub3c4\ub0ae",
            "\uc774\ub3d9\uc801",
            "\uc774\ub3d9\uc744\uc904",
            "lesswalking",
        )
    )


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _has_fast_signal(source_text: str) -> bool:
    lowered = source_text.lower()
    compact = source_text.replace(" ", "")
    return any(token in lowered or token in compact for token in ("fast", "packed", "dense", "busy", "빡빡", "타이트", "꽉채워", "꽉차게", "알차게"))


def _has_early_start_signal(source_text: str) -> bool:
    if _has_late_start_signal(source_text):
        return False
    lowered = source_text.lower()
    compact = source_text.replace(" ", "").lower()
    phrase_tokens = (
        "start early",
        "early start",
        "morning start",
        "early morning",
    )
    compact_tokens = (
        "아침일찍",
        "오전일찍",
        "아침부터",
        "오전부터",
        "일찍시작",
        "일찍출발",
        "이른아침",
        "밤부터시작하지말고",
        "저녁부터시작하지말고",
        "night부터시작하지말고",
        "evening부터시작하지말고",
        "startearly",
        "morningstart",
        "frommorning",
    )
    return any(token in lowered for token in phrase_tokens) or any(token in compact for token in compact_tokens)


def _has_late_start_signal(source_text: str) -> bool:
    lowered = source_text.lower()
    compact = source_text.replace(" ", "")
    return any(
        token in lowered or token in compact
        for token in (
            "late start",
            "start late",
            "늦게시작",
            "늦게시작",
            "아침일찍시작말고",
            "아침일찍말고",
            "일찍시작말고",
            "일찍시작하지말고",
            "아침늦게",
            "일찍움직이기싫",
        )
    )


def _has_budget_save_signal(source_text: str) -> bool:
    lowered = source_text.lower()
    compact = source_text.replace(" ", "")
    return any(
        token in lowered or token in compact
        for token in ("budget", "cheap", "save", "저예산", "가성비", "아끼", "아껴", "무료", "유료입장피", "최대한아끼")
    )


_EIFFEL_LOCK_ALIASES = ("eiffel", "eiffeltower", "toureiffel", "\uc5d0\ud3a0", "\uc5d0\ud3a0\ud0d1")
_SEINE_LOCK_ALIASES = ("seine", "seineriver", "\uc13c\uac15")
_ARC_LOCK_ALIASES = ("arc", "arcdetriomphe", "\uac1c\uc120\ubb38")
_JAZZ_LOCK_ALIASES = ("jazz", "jazzbar", "caveaudelahuchette", "huchette", "\uc7ac\uc988", "\uc7ac\uc988\ubc14", "\uc704\uc158\ud2b8")
_NIGHT_LOCK_CUES = ("night", "nightview", "night_view", "sparkling", "\uc57c\uacbd", "\ubc24", "\uc57c\uac04")
_SUNSET_LOCK_CUES = ("sunset", "\uc11d\uc591", "\uc120\uc14b", "\ub178\uc744", "\ud574\uc9c8\ub158")
_FINAL_LOCK_CUES = ("finish", "final", "end", "\ub9c8\ubb34\ub9ac", "\ub9c8\uc9c0\ub9c9", "\ub05d")


def _compact_source_window(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\uac00-\ud7a3]+", "", str(value or "")).lower()


def _has_scoped_cue(source_text: str, aliases: tuple[str, ...], cues: tuple[str, ...], *, before: int = 12, after: int = 22) -> bool:
    text = _compact_source_window(source_text)
    if not text:
        return False
    cue_values = [_compact_source_window(cue) for cue in cues if _compact_source_window(cue)]
    for alias in aliases:
        alias_value = _compact_source_window(alias)
        if not alias_value:
            continue
        start = text.find(alias_value)
        if start < 0:
            continue
        window = text[max(0, start - before) : start + len(alias_value) + after]
        if any(cue in window for cue in cue_values):
            return True
    return False


def _locked_stop(entity: str, slug: str, target_slot: str, label: str) -> dict[str, Any]:
    return {
        "entity": entity,
        "slug": slug,
        "modifier": "night_view",
        "target_slot": target_slot,
        "locked": True,
        "preferred_day": 1,
        "label": label,
    }


def _has_late_bar_lock_request(must_include: list[str], source_text: str) -> bool:
    if _has_negative_jazz_or_nightlife_signal(source_text):
        return False
    for value in must_include:
        if _constraint_aliases(value).intersection(set(_JAZZ_LOCK_ALIASES)):
            return True
    compact = _compact_source_window(source_text)
    return any(_compact_source_window(alias) in compact for alias in _JAZZ_LOCK_ALIASES)


def _derive_locked_stops(must_include: list[str], night_view_required: bool, source_text: str) -> list[dict[str, Any]]:
    has_seine_request = any(_constraint_aliases(value).intersection({"센강", "seine", "seineriver"}) for value in must_include)
    if not night_view_required and not _has_night_view_signal(source_text) and not _has_late_bar_lock_request(must_include, source_text) and not has_seine_request:
        return []
    locks: list[dict[str, Any]] = []
    has_source_text = bool(str(source_text or "").strip())
    for value in must_include:
        aliases = _constraint_aliases(value)
        if aliases.intersection({"에펠탑", "에펠", "eiffel", "eiffeltower", "toureiffel"}):
            if has_source_text and not _has_scoped_cue(source_text, _EIFFEL_LOCK_ALIASES, _NIGHT_LOCK_CUES):
                continue
            locks.append(_locked_stop("eiffel_tower", "eiffel-tower", "evening", "에펠탑 야경"))
        elif aliases.intersection({"센강", "seine", "seineriver"}):
            has_sunset = _has_scoped_cue(source_text, _SEINE_LOCK_ALIASES, _SUNSET_LOCK_CUES)
            has_night = _has_scoped_cue(source_text, _SEINE_LOCK_ALIASES, _NIGHT_LOCK_CUES)
            has_final = _has_scoped_cue(source_text, _SEINE_LOCK_ALIASES, _FINAL_LOCK_CUES, before=4, after=28)
            target_slot = "night" if has_night and not has_sunset else "evening" if (has_sunset or has_night or has_final) else "afternoon"
            label = "센강 석양 산책" if has_sunset else "센강 야경 산책" if target_slot in {"evening", "night"} else "센강 산책"
            locks.append(_locked_stop("seine_river", "seine-river-walk", target_slot, label))
        elif aliases.intersection({"개선문", "arc", "arcdetriomphe"}):
            has_night = _has_scoped_cue(source_text, _ARC_LOCK_ALIASES, _NIGHT_LOCK_CUES)
            has_final = _has_scoped_cue(source_text, _ARC_LOCK_ALIASES, _FINAL_LOCK_CUES, before=4, after=28)
            if has_source_text and not (has_night or has_final):
                continue
            locks.append(_locked_stop("arc_de_triomphe", "arc-de-triomphe", "night" if has_final else "evening", "개선문 야경"))
        elif aliases.intersection(set(_JAZZ_LOCK_ALIASES)):
            locks.append(_locked_stop("jazz_bar", "caveau-de-la-huchette", "night", "재즈바"))
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
    normalized_style = {
        "romantic" if str(value).lower().strip() == "romance" else str(value).lower().strip()
        for value in travel_style
        if str(value).strip()
    }
    normalized_meal = {str(value).lower() for value in meal_preference if str(value).strip()}
    normalized_must_include = " ".join(str(value).lower() for value in must_include if str(value).strip())
    prefers_cafe_dessert = bool(normalized_style.intersection({"cafe", "dessert"})) or bool(
        normalized_meal.intersection({"cafe", "dessert", "coffee", "bakery"})
    )
    prefers_french_dinner = bool(normalized_meal.intersection({"french", "bistro", "brasserie", "romantic"}))
    prefers_late_bar = bool(normalized_meal.intersection({"jazz", "jazz_bar", "wine", "bar"})) or bool(normalized_style.intersection({"jazz", "nightlife"}))
    romantic_trip = bool(normalized_style.intersection({"romantic"}))
    landmark_trip = bool(normalized_style.intersection({"landmark", "classic"}))
    indoor_trip = bool(normalized_style.intersection({"indoor"}))
    art_trip = bool(normalized_style.intersection({"museum", "art", "culture"}))
    has_eiffel_night = "에펠" in normalized_must_include or "eiffel" in normalized_must_include
    late_start = bool(set(preferred_time_slots).intersection({"afternoon", "evening", "night"}))

    if indoor_trip and prefers_late_bar:
        return ["indoor_culture_day", "indoor_culture_day", "general_landmark_day"]
    if indoor_trip and night_view_required:
        return ["indoor_culture_day", "museum_focused_day", "romantic_evening_day"]
    if indoor_trip:
        return ["indoor_culture_day", "museum_focused_day", "general_landmark_day"]
    if art_trip:
        return ["museum_focused_day", "general_landmark_day", "museum_focused_day"]
    if pace == "slow" and prefers_cafe_dessert and night_view_required and has_eiffel_night and prefers_french_dinner:
        return ["slow_cafe_evening_day", "romantic_evening_day", "slow_cafe_day"]
    if night_view_required and has_eiffel_night:
        return ["night_view_focused_day", "romantic_evening_day", "general_landmark_day"]
    if pace == "slow" and prefers_cafe_dessert:
        return ["slow_cafe_day", "romantic_evening_day" if late_start else "general_landmark_day"]
    if night_view_required:
        return ["romantic_evening_day", "night_view_focused_day"]
    if romantic_trip and pace == "slow" and landmark_trip:
        return ["romantic_evening_day", "general_landmark_day", "slow_cafe_day", "romantic_evening_day"]
    if romantic_trip and pace == "slow":
        return ["romantic_evening_day", "slow_cafe_day", "general_landmark_day"]
    if romantic_trip and landmark_trip:
        return ["romantic_evening_day", "general_landmark_day"]
    if prefers_late_bar or (prefers_french_dinner and late_start):
        return ["romantic_evening_day", "slow_cafe_day"]
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
    indoor_trip = any(str(value).lower() == "indoor" for value in planning_brief.get("travel_style") or [])
    if indoor_trip:
        next_base = ["indoor_culture_day", "museum_focused_day", "slow_cafe_day"]
    elif any(token in lowered for token in ("must_include", "night_view", "nightclimax", "night_climax", "에펠")):
        next_base = ["slow_cafe_evening_day", "romantic_evening_day", "night_view_focused_day"]
    elif any(token in lowered for token in ("helper", "story_flow", "quality")):
        next_base = ["slow_cafe_evening_day", "slow_cafe_day", "romantic_evening_day"]
    else:
        next_base = base or ["general_landmark_day"]
    if previous_blueprints and next_base and previous_blueprints[0] == next_base[0]:
        rotations = ["indoor_culture_day", "romantic_evening_day", "night_view_focused_day", "slow_cafe_day", "general_landmark_day"]
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
        " ".join(str(value) for value in place.get("tags") or []),
        str(item.get("routeAxisLabel") or ""),
    ]
    cuisine = place.get("cuisine")
    if isinstance(cuisine, list):
        values.extend(str(value) for value in cuisine if value)
    elif cuisine:
        values.append(str(cuisine))
    return _normalize_name(" ".join(values))


def _item_identity_text(item: dict[str, Any]) -> str:
    place = item.get("place") or {}
    values = [
        str(place.get("name") or ""),
        str(item.get("title") or ""),
        str(place.get("slug") or ""),
        str(place.get("place_id") or ""),
        str(place.get("category") or ""),
    ]
    return _normalize_name(" ".join(values))


def _canonical_entry_match(entry: str, canonical: str) -> bool:
    if canonical == "eiffel":
        return "eiffeltower" in entry or ("eiffel" in entry and "landmark" in entry)
    if canonical == "louvre":
        return "louvremuseum" in entry or ("louvre" in entry and "museum" in entry)
    if canonical == "orsay":
        return "museedorsay" in entry or ("orsay" in entry and "museum" in entry)
    if canonical == "seine":
        return "seineriverwalk" in entry or ("seine" in entry and "landmark" in entry)
    if canonical == "notre":
        return "notredame" in entry and ("cathedral" in entry or "landmark" in entry)
    if canonical == "sainte":
        return ("saintechapelle" in entry or "saintchapelle" in entry) and "cathedral" in entry
    if canonical == "marais":
        return ("lemarais" in entry or "marais" in entry) and "neighborhood" in entry
    if canonical == "saint_germain":
        return (
            "saintgermain" in entry and "despres" in entry
        ) or ("saintgermain" in entry and ("neighborhood" in entry or "landmark" in entry))
    if canonical == "montmartre":
        return ("montmartre" in entry or "몽마르트" in entry) and "neighborhood" in entry
    if canonical == "arc":
        return "arcdetriomphe" in entry or ("arc" in entry and "triomphe" in entry) or "개선문" in entry
    if canonical == "champs":
        return "champselysees" in entry and ("neighborhood" in entry or "landmark" in entry)
    if canonical == "luxembourg":
        return "luxembourggardens" in entry or ("luxembourg" in entry and "park" in entry)
    if canonical == "tuileries":
        return "tuileriesgarden" in entry or ("tuileries" in entry and "park" in entry)
    if canonical == "garnier":
        return "palaisgarnier" in entry or ("garnier" in entry and "landmark" in entry)
    if canonical == "palais_royal":
        return "palaisroyal" in entry or ("팔레루아얄" in entry and "landmark" in entry)
    if canonical == "jazz":
        return ("caveaudelahuchette" in entry or "huchette" in entry or "재즈바" in entry) and "bar" in entry
    return False


def _constraint_matches_catalog(value: str, catalog: list[str]) -> bool:
    aliases = _constraint_aliases(value)
    canonical = _canonical_place_key(value)
    for entry in catalog:
        if not entry:
            continue
        if canonical:
            if _canonical_entry_match(entry, canonical):
                return True
            continue
        for alias in aliases:
            if alias == "arc" and "arcdetriomphe" not in entry and "\uac1c\uc120\ubb38" not in entry:
                continue
            if alias == "opera" and "garnier" not in entry and "palaisgarnier" not in entry:
                continue
            if alias in entry or entry in alias:
                return True
    return False


def _constraint_aliases(value: str) -> set[str]:
    normalized = _normalize_name(value)
    aliases = {normalized}
    for group in PLACE_ALIAS_GROUPS:
        if any(alias in normalized or normalized in alias for alias in group if alias):
            aliases.update(group)
    return {alias for alias in aliases if alias}


def _item_start_minutes(item: dict[str, Any]) -> int | None:
    raw = str(item.get("start_time") or "").strip()
    if ":" not in raw:
        return None
    try:
        hour, minute = raw.split(":", 1)
        return int(hour) * 60 + int(minute)
    except (TypeError, ValueError):
        return None


def _is_named_night_climax(item: dict[str, Any]) -> bool:
    if str(item.get("time_slot") or "") not in {"evening", "night"}:
        start_minutes = _item_start_minutes(item)
        if start_minutes is None or start_minutes < 18 * 60:
            return False
    text = _item_search_text(item)
    return any(
        token in text
        for token in (
            "eiffel",
            "eiffeltower",
            "에펠",
            "에펠탑",
            "seine",
            "seineriver",
            "센강",
            "세느강",
            "arc",
            "arcdetriomphe",
            "개선문",
            "montmartre",
            "몽마르트",
        )
    )


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
