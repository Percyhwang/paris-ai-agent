from __future__ import annotations

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
    night_view_required = bool(preferences.get("night_view_required")) or "night_view" in {
        value.lower() for value in travel_style
    } or _has_night_view_signal(source_text)
    pace_level = str(pace.get("level") or _pace_from_style(travel_style) or "normal").lower()
    if pace_level == "normal" and _has_slow_signal(source_text):
        pace_level = "slow"
    start_time, end_time = _slot_window(preferred_time_slots)

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
            "budget_mode": budget.get("budget_mode") or "normal",
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

    if not next_must_include and ("에펠" in source_text or "eiffel" in lowered):
        next_must_include = _merge_unique(next_must_include, ["에펠탑"])
    if ("루브르" in source_text or "louvre" in lowered) and any(
        token in lowered for token in ("말고", "제외", "않", "싫", "avoid", "without", "don't", "dont")
    ):
        next_must_avoid = _merge_unique(next_must_avoid, ["루브르 박물관"])
    if _has_night_view_signal(source_text):
        next_travel_style = _merge_unique(next_travel_style, ["night_view"])
        next_preferred_slots = _merge_unique(next_preferred_slots, ["evening", "night"])
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
    return next_must_include, next_must_avoid, next_preferred_slots, next_meal_preference, next_travel_style


def _has_night_view_signal(source_text: str) -> bool:
    lowered = source_text.lower()
    return any(token in lowered for token in ("night view", "night_view", "sparkling", "야경", "석양", "선셋", "야간"))


def _has_slow_signal(source_text: str) -> bool:
    lowered = source_text.lower()
    return any(token in lowered for token in ("slow", "relax", "relaxed", "healing", "천천히", "여유", "느긋", "많이 돌아다니는 건 싫"))


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


_ADAPTERS = {
    Intent.CREATE_PLAN: _create_trip_brief,
    Intent.MODIFY_PLAN: _modify_trip_brief,
    Intent.HOTEL_SEARCH: _hotel_brief,
    Intent.HOTEL_BOOK: _hotel_brief,
    Intent.ESTIMATE_BUDGET: _budget_brief,
    Intent.RECOMMEND_VENUE: _venue_brief,
    Intent.OPTIMIZE_ROUTE: _route_brief,
}
