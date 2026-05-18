from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from parser_api.intents import Intent
from parser_api.parsers.shared.planning_brief_schema import ConstraintSpec, PlanningBriefPayload

_INTENT_NAMES = {
    Intent.CREATE_PLAN: "create_trip",
    Intent.MODIFY_PLAN: "modify_trip",
    Intent.HOTEL_SEARCH: "hotel_search",
    Intent.HOTEL_BOOK: "hotel_book",
    Intent.ESTIMATE_BUDGET: "budget_adjust",
    Intent.RECOMMEND_VENUE: "restaurant_search",
    Intent.OPTIMIZE_ROUTE: "route_optimize",
}

PLACE_CANONICALS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("에펠탑", ("에펠탑", "에펠", "eiffel tower", "eiffel")),
    ("루브르 박물관", ("루브르 박물관", "루브르", "louvre museum", "louvre")),
    ("오르세 미술관", ("오르세 미술관", "오르세", "orsay", "musee d'orsay", "musée d'orsay")),
    ("개선문", ("개선문", "arc de triomphe", "arc")),
    ("샹젤리제 거리", ("샹젤리제 거리", "샹젤리제", "champs elysees", "champs-élysées")),
    ("몽마르트르", ("몽마르트르", "몽마르트", "사크레쾨르", "사크레 쾨르", "sacre coeur", "sacré-cœur", "montmartre")),
    ("마레 지구", ("마레 지구", "마레", "le marais", "marais")),
    ("센강 산책", ("센강", "세느강", "seine river", "seine")),
    ("노트르담 대성당", ("노트르담 대성당", "노트르담", "notre dame")),
    ("생트샤펠", ("생트샤펠", "생트 샤펠", "sainte chapelle", "sainte-chapelle", "saint chapelle")),
    ("튈르리 정원", ("튈르리 정원", "튈르리", "tuileries")),
    ("뤽상부르 공원", ("뤽상부르 공원", "뤽상부르", "룩셈부르크 공원", "룩셈부르크", "luxembourg gardens", "luxembourg")),
    ("오페라 가르니에", ("오페라 가르니에", "오페라", "가르니에", "팔레 가르니에", "palais garnier", "palais-garnier", "opera garnier", "opera")),
    ("팔레 루아얄", ("팔레 루아얄", "팔레루아얄", "palais royal", "palais-royal", "palaisroyal")),
    ("르 카보 드 라 위셰트", ("르 카보 드 라 위셰트", "재즈바", "재즈 바", "jazz bar", "jazz", "caveau de la huchette", "huchette")),
)

INCLUDE_CUES = ("꼭", "반드시", "무조건", "포함", "넣", "가고싶", "보고싶", "방문", "핵심", "보고", "산책", "마무리", "시작", "visit", "must", "include")
AVOID_CUES = ("빼", "제외", "말고", "없는", "없이", "가지않", "안가", "넣지", "피하", "싫", "avoid", "without", "skip", "exclude")


def build_unified_planning_brief(
    intent: Intent | str,
    parsed_payload: Any,
    context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    resolved_intent = intent if isinstance(intent, Intent) else Intent(str(intent))
    payload = _payload_dict(parsed_payload)
    normalized_context = dict(context or {})
    adapter = _ADAPTERS.get(resolved_intent)
    if adapter is None:
        return None
    return adapter(payload, normalized_context)


def attach_planning_brief(
    data: dict[str, Any],
    *,
    intent: Intent | str,
    parsed_payload: Any,
    context: dict[str, Any] | None = None,
    data_key: str | None = None,
) -> dict[str, Any]:
    brief = build_unified_planning_brief(intent, parsed_payload, context)
    if not brief:
        return data
    enriched = dict(data)
    enriched["planning_brief"] = brief
    if data_key:
        nested = enriched.get(data_key)
        if isinstance(nested, dict):
            nested_payload = dict(nested)
            nested_payload.setdefault("_planning_brief", brief)
            enriched[data_key] = nested_payload
    return enriched


def _create_trip_brief(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    preferences = payload.get("preferences") if isinstance(payload.get("preferences"), dict) else {}
    dates = payload.get("dates") if isinstance(payload.get("dates"), dict) else {}
    pace = payload.get("pace") if isinstance(payload.get("pace"), dict) else {}
    mobility = payload.get("mobility") if isinstance(payload.get("mobility"), dict) else {}
    budget = payload.get("budget") if isinstance(payload.get("budget"), dict) else {}
    lodging = payload.get("lodging") if isinstance(payload.get("lodging"), dict) else {}
    source_text = str(context.get("message") or payload.get("_source_message") or "").strip()

    must_include = _string_list(preferences.get("must_include"))
    must_avoid = _string_list(preferences.get("must_avoid"))
    travel_style = _merge_unique(
        _string_list(preferences.get("travel_style")),
        _string_list(preferences.get("themes")),
        _string_list(context.get("style_tags")),
    )
    preferred_time_slots = _string_list(preferences.get("preferred_time_slots"))
    meal_preference = _string_list(preferences.get("meal_preference"))
    must_include, must_avoid, preferred_time_slots, meal_preference, travel_style = _apply_text_fallbacks(
        source_text=source_text,
        must_include=must_include,
        must_avoid=must_avoid,
        preferred_time_slots=preferred_time_slots,
        meal_preference=meal_preference,
        travel_style=travel_style,
    )
    must_include, must_avoid = _resolve_place_preference_conflicts(must_include, must_avoid)
    night_view_required = bool(preferences.get("night_view_required")) or "night_view" in {
        value.lower() for value in travel_style
    } or _has_night_view_signal(source_text)
    pace_level = str(pace.get("level") or _pace_from_style(travel_style) or "normal").lower()
    if pace_level == "normal" and _has_slow_signal(source_text):
        pace_level = "slow"
    if pace_level == "normal" and _has_fast_signal(source_text):
        pace_level = "fast"
    start_time, end_time = _slot_window(preferred_time_slots)

    budget_mode = budget.get("budget_mode") or ("save" if _has_budget_save_signal(source_text) else "normal")

    return PlanningBriefPayload(
        intent=_INTENT_NAMES[Intent.CREATE_PLAN],
        trip_days=_coerce_int(dates.get("days") or context.get("total_days")),
        destination=str((payload.get("destination") or {}).get("city") or context.get("destination") or "Paris"),
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
        transport_preference=str(mobility.get("travel_mode") or "both").lower(),
        start_time=start_time,
        end_time=end_time,
        hard_constraints=_constraints_from_places(must_include, must_avoid, night_view_required),
        soft_constraints=_soft_constraints(
            preferred_time_slots=preferred_time_slots,
            meal_preference=meal_preference,
            pace=pace_level,
            travel_style=travel_style,
        ),
        source_text=source_text,
    ).model_dump(mode="json")


def _modify_trip_brief(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    operations = [item for item in payload.get("operations") or [] if isinstance(item, dict)]
    source_text = str(context.get("message") or "").strip()
    must_include = _merge_unique(
        [
            str((operation.get("constraints_patch") or {}).get("to_place") or operation.get("place_name") or "").strip()
            for operation in operations
            if operation.get("op") in {"add", "replace", "move"}
        ]
    )
    must_avoid = _merge_unique(
        [
            str((operation.get("constraints_patch") or {}).get("from_place") or operation.get("place_name") or "").strip()
            for operation in operations
            if operation.get("op") in {"remove", "replace"}
        ]
    )
    preferred_time_slots = _merge_unique(
        [
            str(operation.get("target_slot") or "").replace("dinner", "evening").strip()
            for operation in operations
            if operation.get("target_slot")
        ]
    )
    must_include, must_avoid, preferred_time_slots, _, travel_style = _apply_text_fallbacks(
        source_text=source_text,
        must_include=must_include,
        must_avoid=must_avoid,
        preferred_time_slots=preferred_time_slots,
        meal_preference=[],
        travel_style=_string_list(context.get("style_tags")),
    )
    pace_level = next(
        (
            str(operation.get("pace") or "").lower()
            for operation in operations
            if str(operation.get("pace") or "").lower() in {"slow", "normal", "fast"}
        ),
        "",
    ) or _pace_from_style(travel_style) or "normal"
    if pace_level == "normal" and _has_slow_signal(source_text):
        pace_level = "slow"
    if pace_level == "normal" and _has_fast_signal(source_text):
        pace_level = "fast"
    night_view_required = any("night" in style.lower() or "야경" in style for style in travel_style) or _has_night_view_signal(source_text)
    start_time, end_time = _slot_window(preferred_time_slots)

    return PlanningBriefPayload(
        intent=_INTENT_NAMES[Intent.MODIFY_PLAN],
        trip_days=_coerce_int(context.get("total_days")),
        destination=str(context.get("destination") or "Paris"),
        must_include=must_include,
        must_avoid=must_avoid,
        preferred_time_slots=preferred_time_slots,
        meal_preference=[],
        night_view_required=night_view_required,
        pace=pace_level,
        travel_style=travel_style,
        budget_range={},
        hotel_area_preference=None,
        transport_preference="both",
        start_time=start_time,
        end_time=end_time,
        hard_constraints=_constraints_from_places(must_include, must_avoid, night_view_required),
        soft_constraints=_soft_constraints(
            preferred_time_slots=preferred_time_slots,
            meal_preference=[],
            pace=pace_level,
            travel_style=travel_style,
        ),
        source_text=source_text,
    ).model_dump(mode="json")


def _hotel_brief(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    destination = payload.get("destination") if isinstance(payload.get("destination"), dict) else {}
    budget_cap = payload.get("max_price_per_night")
    hotel_area_preference = payload.get("area") or payload.get("landmark")
    return PlanningBriefPayload(
        intent=_INTENT_NAMES[Intent.HOTEL_SEARCH],
        trip_days=_coerce_int(payload.get("nights") or context.get("total_days")),
        destination=str(destination.get("city") or destination.get("landmark") or context.get("destination") or "Paris"),
        must_include=[],
        must_avoid=[],
        preferred_time_slots=[],
        meal_preference=[],
        night_view_required=False,
        pace="normal",
        travel_style=[],
        budget_range={
            "currency": payload.get("currency") or "EUR",
            "budget_total": budget_cap,
            "budget_per_day": budget_cap,
            "budget_mode": "normal",
        },
        hotel_area_preference=str(hotel_area_preference or "").strip() or None,
        transport_preference=str(context.get("travel_mode") or "both").lower(),
        hard_constraints=[],
        soft_constraints=_soft_constraints(
            preferred_time_slots=[],
            meal_preference=[],
            pace="normal",
            travel_style=[],
        ),
    ).model_dump(mode="json")


def _budget_brief(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    destination = payload.get("destination") if isinstance(payload.get("destination"), dict) else {}
    dates = payload.get("dates") if isinstance(payload.get("dates"), dict) else {}
    budget = payload.get("budget") if isinstance(payload.get("budget"), dict) else {}
    return PlanningBriefPayload(
        intent=_INTENT_NAMES[Intent.ESTIMATE_BUDGET],
        trip_days=_coerce_int(dates.get("days") or context.get("total_days")),
        destination=str(destination.get("city") or context.get("destination") or "Paris"),
        must_include=[],
        must_avoid=[],
        preferred_time_slots=[],
        meal_preference=[],
        night_view_required=False,
        pace="normal",
        travel_style=[],
        budget_range={
            "currency": budget.get("currency") or payload.get("currency") or "EUR",
            "budget_total": budget.get("budget_total"),
            "budget_per_day": budget.get("budget_per_day"),
            "budget_mode": budget.get("budget_mode") or "normal",
        },
        hotel_area_preference=None,
        transport_preference="both",
        hard_constraints=[],
        soft_constraints=[],
    ).model_dump(mode="json")


def _venue_brief(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    destination = payload.get("destination") if isinstance(payload.get("destination"), dict) else {}
    budget = payload.get("budget") if isinstance(payload.get("budget"), dict) else {}
    venue_type = str(payload.get("venue_type") or "attraction")
    themes = _merge_unique(_string_list(payload.get("themes")), [venue_type])
    meal_preference = [venue_type] if venue_type in {"restaurant", "cafe"} else []
    must_include = _string_list(payload.get("must_include"))
    must_avoid = _string_list(payload.get("must_avoid"))
    return PlanningBriefPayload(
        intent=_INTENT_NAMES[Intent.RECOMMEND_VENUE],
        trip_days=_coerce_int(context.get("total_days")),
        destination=str(destination.get("city") or context.get("destination") or "Paris"),
        must_include=must_include,
        must_avoid=must_avoid,
        preferred_time_slots=[],
        meal_preference=meal_preference,
        night_view_required=False,
        pace="normal",
        travel_style=themes,
        budget_range={
            "currency": budget.get("currency") or "EUR",
            "budget_total": budget.get("budget_total"),
            "budget_per_day": budget.get("budget_per_day"),
            "budget_mode": budget.get("budget_mode") or "normal",
        },
        hotel_area_preference=str(payload.get("area") or payload.get("landmark") or "").strip() or None,
        transport_preference="both",
        hard_constraints=_constraints_from_places(must_include, must_avoid, False),
        soft_constraints=_soft_constraints(
            preferred_time_slots=[],
            meal_preference=meal_preference,
            pace="normal",
            travel_style=themes,
        ),
    ).model_dump(mode="json")


def _route_brief(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    route_points = [str((point or {}).get("name") or "").strip() for point in payload.get("route_points") or []]
    route_points = [value for value in route_points if value]
    return PlanningBriefPayload(
        intent=_INTENT_NAMES[Intent.OPTIMIZE_ROUTE],
        trip_days=_coerce_int(context.get("total_days")),
        destination=str(context.get("destination") or "Paris"),
        must_include=route_points,
        must_avoid=[],
        preferred_time_slots=[],
        meal_preference=[],
        night_view_required=False,
        pace="normal",
        travel_style=[],
        budget_range={},
        hotel_area_preference=None,
        transport_preference=str(payload.get("travel_mode") or "both").lower(),
        hard_constraints=_constraints_from_places(route_points, [], False),
        soft_constraints=[],
    ).model_dump(mode="json")


def _payload_dict(parsed_payload: Any) -> dict[str, Any]:
    if hasattr(parsed_payload, "model_dump"):
        return deepcopy(parsed_payload.model_dump())
    if isinstance(parsed_payload, dict):
        return deepcopy(parsed_payload)
    raise TypeError("Unsupported parsed payload")


def _constraints_from_places(
    must_include: list[str],
    must_avoid: list[str],
    night_view_required: bool,
) -> list[ConstraintSpec]:
    constraints = [
        ConstraintSpec(
            id=f"must_include_{_slugify(value)}",
            type="must_include",
            value=value,
            priority="hard",
            source="user",
        )
        for value in must_include
    ]
    constraints.extend(
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
        constraints.append(
            ConstraintSpec(
                id="night_view_required",
                type="night_view_required",
                value=True,
                priority="hard",
                source="user",
            )
        )
    return constraints


def _soft_constraints(
    *,
    preferred_time_slots: list[str],
    meal_preference: list[str],
    pace: str,
    travel_style: list[str],
) -> list[ConstraintSpec]:
    constraints: list[ConstraintSpec] = []
    if preferred_time_slots:
        constraints.append(
            ConstraintSpec(
                id="preferred_time_slots",
                type="preferred_time_slots",
                value=preferred_time_slots,
                priority="soft",
                source="parser",
            )
        )
    if meal_preference:
        constraints.append(
            ConstraintSpec(
                id="meal_preference",
                type="meal_preference",
                value=meal_preference,
                priority="soft",
                source="parser",
            )
        )
    if pace:
        constraints.append(
            ConstraintSpec(
                id="pace",
                type="pace",
                value=pace,
                priority="soft",
                source="parser",
            )
        )
    if travel_style:
        constraints.append(
            ConstraintSpec(
                id="travel_style",
                type="travel_style",
                value=travel_style,
                priority="soft",
                source="parser",
            )
        )
    return constraints


def _slot_window(preferred_time_slots: list[str]) -> tuple[str | None, str | None]:
    if not preferred_time_slots:
        return None, None
    normalized = [slot for slot in preferred_time_slots if slot in {"morning", "lunch", "afternoon", "evening", "night"}]
    if not normalized:
        return None, None
    start_map = {
        "morning": "09:00",
        "lunch": "12:00",
        "afternoon": "15:00",
        "evening": "18:30",
        "night": "20:30",
    }
    end_map = {
        "morning": "11:30",
        "lunch": "14:00",
        "afternoon": "17:30",
        "evening": "21:00",
        "night": "23:00",
    }
    start_time = start_map.get(normalized[0])
    end_time = end_map.get(normalized[-1])
    return start_time, end_time


def _pace_from_style(values: list[str]) -> str | None:
    lowered = {value.lower() for value in values if value}
    if {"slow", "relax", "healing", "여유", "휴식"} & lowered:
        return "slow"
    if {"fast", "packed", "dense", "빡빡", "타이트"} & lowered:
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
    next_preferred_slots = list(preferred_time_slots)
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
    if _has_generic_river_walk_signal(source_text):
        text_include = _merge_unique(text_include, ["센강 산책"])
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
        _avoid_cue_after_alias(source_text, alias, window=10)
        for alias in ("에펠", "에펠탑", "eiffel")
    )
    if not next_must_include and eiffel_requested:
        next_must_include = _merge_unique(next_must_include, ["에펠탑"])
    elif eiffel_requested and _has_night_view_signal(source_text):
        next_must_include = _merge_unique(next_must_include, ["에펠탑"])
    if _has_budget_save_signal(source_text):
        next_travel_style = _merge_unique(next_travel_style, ["budget", "walk"])
    if _has_late_start_signal(source_text):
        next_preferred_slots = _merge_unique(next_preferred_slots, ["afternoon"])
    elif "오후" in source_text:
        next_preferred_slots = _merge_unique(next_preferred_slots, ["afternoon"])
    if _has_night_view_signal(source_text):
        next_travel_style = _merge_unique(next_travel_style, ["night_view"])
        next_preferred_slots = _merge_unique(next_preferred_slots, ["evening", "night"])
    if any(token in lowered for token in ("sunset", "석양", "선셋")):
        next_preferred_slots = _merge_unique(next_preferred_slots, ["evening"])
    if any(token in lowered for token in ("brunch", "브런치", "늦은 아침", "늦은아침")):
        next_meal_preference = _merge_unique(next_meal_preference, ["brunch"])
        next_travel_style = _merge_unique(next_travel_style, ["cafe", "foodie"])
        next_preferred_slots = _merge_unique(next_preferred_slots, ["morning", "lunch"])
    if any(token in lowered for token in ("dinner", "디너", "저녁 식사", "저녁은", "프렌치 디너")):
        next_preferred_slots = _merge_unique(next_preferred_slots, ["evening"])
    if any(token in lowered for token in ("cafe", "coffee", "카페")):
        next_meal_preference = _merge_unique(next_meal_preference, ["cafe"])
        next_travel_style = _merge_unique(next_travel_style, ["cafe", "foodie"])
    if any(token in lowered for token in ("dessert", "bakery", "디저트", "베이커리")):
        next_meal_preference = _merge_unique(next_meal_preference, ["dessert"])
        next_travel_style = _merge_unique(next_travel_style, ["dessert", "foodie"])
    if any(token in lowered for token in ("french", "프렌치", "브라세리", "비스트로")):
        next_meal_preference = _merge_unique(next_meal_preference, ["french", "bistro"])
        next_preferred_slots = _merge_unique(next_preferred_slots, ["evening"])
    jazz_avoided = any(_avoid_cue_after_alias(source_text, token, window=10) for token in ("jazz", "재즈", "재즈바", "jazz bar"))
    if any(token in lowered for token in ("jazz", "재즈", "재즈바", "jazz bar")) and not jazz_avoided:
        next_meal_preference = _merge_unique(next_meal_preference, ["jazz_bar"])
        next_travel_style = _merge_unique(next_travel_style, ["jazz", "nightlife", "local"])
        next_preferred_slots = _merge_unique(next_preferred_slots, ["evening", "night"])
    elif jazz_avoided:
        next_meal_preference = [value for value in next_meal_preference if str(value).lower() not in {"jazz", "jazz_bar", "bar", "wine"}]
        next_travel_style = [value for value in next_travel_style if str(value).lower() not in {"jazz", "nightlife"}]
    if any(token in lowered for token in ("local", "로컬", "골목", "마레")):
        next_travel_style = _merge_unique(next_travel_style, ["local"])
    if any(token in lowered for token in ("photo", "사진", "포토", "인생샷")):
        next_travel_style = _merge_unique(next_travel_style, ["photo"])
    if _has_slow_signal(source_text):
        next_travel_style = _merge_unique(next_travel_style, ["slow"])
    next_must_include, next_must_avoid = _resolve_place_preference_conflicts(next_must_include, next_must_avoid)
    return next_must_include, next_must_avoid, next_preferred_slots, next_meal_preference, next_travel_style


def _extract_place_preferences_from_text(source_text: str) -> tuple[list[str], list[str]]:
    include: list[str] = []
    avoid: list[str] = []
    segments = [segment for segment in re.split(r"[.!?\n。！？]+", source_text) if segment.strip()] or [source_text]

    for canonical, aliases in PLACE_CANONICALS:
        if not _contains_alias(source_text, aliases):
            continue
        if any(_avoid_cue_after_alias(source_text, alias, window=8) and not _photo_marker_near_alias(source_text, alias) for alias in aliases):
            avoid.append(canonical)
            continue
        if any(_photo_marker_near_alias(source_text, alias) for alias in aliases):
            include.append(canonical)
            continue
        if any(_only_marker_after_alias(source_text, alias) for alias in aliases):
            include.append(canonical)
            continue
        if any(_cue_after_alias(source_text, alias, INCLUDE_CUES, window=28) for alias in aliases):
            include.append(canonical)
            continue
        for segment in segments:
            if not _contains_alias(segment, aliases):
                continue
            alias_index = _first_alias_index(segment, aliases)
            include_index = _first_cue_index_after(segment, INCLUDE_CUES, alias_index)
            avoid_index = _first_cue_index_after(segment, AVOID_CUES, alias_index)
            if (
                alias_index >= 0
                and avoid_index >= 0
                and avoid_index - alias_index <= 18
                and not (include_index >= 0 and include_index < avoid_index)
            ):
                avoid.append(canonical)
                break
            if include_index < 0:
                continue
            if alias_index >= 0 and (avoid_index < 0 or include_index < avoid_index):
                include.append(canonical)
                break
        else:
            compact = source_text.replace(" ", "")
            if canonical == "센강 산책" and _has_night_view_signal(source_text):
                include.append(canonical)
            elif canonical == "몽마르트르" and any(token in compact for token in ("몽마르트", "사크레쾨르")):
                include.append(canonical)
            else:
                include.append(canonical)

    return _merge_unique(include), _merge_unique(avoid)


def _contains_alias(text: str, aliases: tuple[str, ...]) -> bool:
    normalized = _normalize_name(text)
    lowered = text.lower()
    return any(_normalize_name(alias) in normalized or alias.lower() in lowered for alias in aliases)


def _cue_after_alias(text: str, alias: str, cues: tuple[str, ...], *, window: int) -> bool:
    normalized = _normalize_name(text)
    normalized_alias = _normalize_name(alias)
    index = normalized.find(normalized_alias)
    if index < 0:
        return False
    after_start = index + len(normalized_alias)
    after = normalized[after_start : after_start + window]
    next_alias_offset = _next_alias_offset(after)
    if next_alias_offset >= 0:
        after = after[:next_alias_offset]
    return any(_normalize_name(cue) in after for cue in cues)


def _avoid_cue_after_alias(text: str, alias: str, *, window: int) -> bool:
    normalized = _normalize_name(text)
    normalized_alias = _normalize_name(alias)
    index = normalized.find(normalized_alias)
    if index < 0:
        return False
    after_start = index + len(normalized_alias)
    after = normalized[after_start : after_start + window]
    next_alias_offset = _next_alias_offset(after)
    if next_alias_offset >= 0:
        after = after[:next_alias_offset]
    avoid_positions = [after.find(_normalize_name(cue)) for cue in AVOID_CUES if _normalize_name(cue) in after]
    if not avoid_positions:
        return False
    avoid_index = min(avoid_positions)
    include_positions = [after.find(_normalize_name(cue)) for cue in INCLUDE_CUES if _normalize_name(cue) in after]
    return not include_positions or min(include_positions) > avoid_index


def _photo_marker_near_alias(text: str, alias: str) -> bool:
    normalized = _normalize_name(text)
    normalized_alias = _normalize_name(alias)
    index = normalized.find(normalized_alias)
    if index < 0:
        return False
    window = normalized[max(0, index - 4) : index + len(normalized_alias) + 14]
    return any(token in window for token in ("사진만", "사진찍", "사진", "포토", "photo", "외관만"))


def _only_marker_after_alias(text: str, alias: str) -> bool:
    normalized = _normalize_name(text)
    normalized_alias = _normalize_name(alias)
    index = normalized.find(normalized_alias)
    if index < 0:
        return False
    return normalized[index + len(normalized_alias) : index + len(normalized_alias) + 3].startswith("만")


def _next_alias_offset(text: str) -> int:
    offsets = [
        text.find(_normalize_name(alias))
        for _, aliases in PLACE_CANONICALS
        for alias in aliases
        if _normalize_name(alias) and _normalize_name(alias) in text
    ]
    return min(offsets) if offsets else -1


def _first_alias_index(text: str, aliases: tuple[str, ...]) -> int:
    normalized = _normalize_name(text)
    indices = [normalized.find(_normalize_name(alias)) for alias in aliases if _normalize_name(alias) in normalized]
    return min(indices) if indices else -1


def _first_cue_index(text: str, cues: tuple[str, ...]) -> int:
    normalized = _normalize_name(text)
    indices = [normalized.find(_normalize_name(cue)) for cue in cues if _normalize_name(cue) in normalized]
    return min(indices) if indices else -1


def _first_cue_index_after(text: str, cues: tuple[str, ...], alias_index: int) -> int:
    if alias_index < 0:
        return -1
    normalized = _normalize_name(text)
    indices = [
        index
        for cue in cues
        if (normalized_cue := _normalize_name(cue))
        and (index := normalized.find(normalized_cue, alias_index)) >= 0
    ]
    return min(indices) if indices else -1


def _resolve_place_preference_conflicts(must_include: list[str], must_avoid: list[str]) -> tuple[list[str], list[str]]:
    avoids = _merge_unique(must_avoid)
    avoid_aliases = {_normalize_name(value) for value in avoids}
    for avoided in avoids:
        for canonical, aliases in PLACE_CANONICALS:
            if _normalize_name(avoided) == _normalize_name(canonical) or any(_normalize_name(alias) == _normalize_name(avoided) for alias in aliases):
                avoid_aliases.add(_normalize_name(canonical))
                avoid_aliases.update(_normalize_name(alias) for alias in aliases)
    filtered = [
        value
        for value in _merge_unique(must_include)
        if _normalize_name(value) not in avoid_aliases
    ]
    return filtered, avoids


def _remove_place_aliases(values: list[str], removals: list[str]) -> list[str]:
    removal_aliases = {_normalize_name(value) for value in removals}
    for removed in removals:
        for canonical, aliases in PLACE_CANONICALS:
            if _normalize_name(removed) == _normalize_name(canonical) or any(_normalize_name(alias) == _normalize_name(removed) for alias in aliases):
                removal_aliases.add(_normalize_name(canonical))
                removal_aliases.update(_normalize_name(alias) for alias in aliases)
    return [value for value in values if _normalize_name(value) not in removal_aliases]


def _has_museum_avoid_signal(source_text: str) -> bool:
    compact = _normalize_name(source_text)
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
    if any(token in compact for token in ("루브르", "오르세")):
        return False
    return any(token in compact for token in ("미술관", "박물관", "전시"))


def _has_generic_park_signal(source_text: str) -> bool:
    compact = _normalize_name(source_text)
    if any(token in compact for token in ("뤽상부르", "룩셈부르크", "튈르리")):
        return False
    return any(token in compact for token in ("공원", "정원", "garden", "park", "피크닉"))


def _has_generic_river_walk_signal(source_text: str) -> bool:
    compact = _normalize_name(source_text)
    if any(token in compact for token in ("센강", "세느강", "seine")):
        return False
    if any(token in compact for token in ("강변", "강가", "강변산책", "riverwalk", "riverside")):
        return True
    return "산책" in compact and any(token in compact for token in ("전망", "풍경", "석양", "노을", "다양", "섞"))


def _has_diversity_signal(source_text: str) -> bool:
    compact = _normalize_name(source_text)
    return any(token in compact for token in ("다양", "섞인", "섞어", "반복하지말고", "반복하지마"))


def _has_orsay_only_signal(source_text: str) -> bool:
    compact = _normalize_name(source_text)
    return "오르세만" in compact or "오르세미술관만" in compact


def _has_night_view_signal(source_text: str) -> bool:
    lowered = source_text.lower()
    has_sunset = any(token in lowered for token in ("sunset", "석양", "선셋", "노을", "해질녘"))
    if _has_negative_night_view_signal(source_text) and not has_sunset:
        return False
    return has_sunset or any(token in lowered for token in ("night view", "night_view", "sparkling", "야경", "야간", "밤"))


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
        )
    ) or any(token in lowered for token in ("no night view", "without night view", "skip night view"))


def _has_slow_signal(source_text: str) -> bool:
    lowered = source_text.lower()
    compact = source_text.replace(" ", "")
    return any(
        token in lowered or token in compact
        for token in (
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
            "장소는적게",
            "4곳이하",
            "세곳정도",
        )
    )


def _has_fast_signal(source_text: str) -> bool:
    lowered = source_text.lower()
    compact = source_text.replace(" ", "")
    return any(token in lowered or token in compact for token in ("fast", "packed", "dense", "busy", "빡빡", "타이트", "꽉채워", "알차게"))


def _has_late_start_signal(source_text: str) -> bool:
    lowered = source_text.lower()
    compact = source_text.replace(" ", "")
    return any(
        token in lowered or token in compact
        for token in (
            "late start",
            "start late",
            "늦게시작",
            "아침일찍시작말고",
            "아침일찍말고",
            "일찍시작말고",
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


def _merge_unique(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in group:
            token = str(value or "").strip()
            if not token:
                continue
            normalized = token.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            merged.append(token)
    return merged


def _string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _slugify(value: str) -> str:
    token = "".join(char.lower() if char.isalnum() else "_" for char in str(value))
    return "_".join(part for part in token.split("_") if part) or "constraint"


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9가-힣]+", "", value.lower())


_ADAPTERS = {
    Intent.CREATE_PLAN: _create_trip_brief,
    Intent.MODIFY_PLAN: _modify_trip_brief,
    Intent.HOTEL_SEARCH: _hotel_brief,
    Intent.HOTEL_BOOK: _hotel_brief,
    Intent.ESTIMATE_BUDGET: _budget_brief,
    Intent.RECOMMEND_VENUE: _venue_brief,
    Intent.OPTIMIZE_ROUTE: _route_brief,
}
