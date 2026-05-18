from __future__ import annotations

from typing import Any

from app.schemas.agent_action_schema import AgentActionPlan


def compose_create_itinerary_payload(
    payload: dict[str, Any],
    *,
    controller_action: AgentActionPlan | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Attach stable frontend-facing fields without removing legacy fields."""

    next_payload = dict(payload)
    trip = dict(next_payload.get("trip") or {})
    days = list(next_payload.get("itinerary_days") or [])
    places = _extract_places(days)
    route_legs = _extract_route_legs(days)
    schedule = _extract_schedule(days)
    evaluation = trip.get("agent_evaluation") or next_payload.get("agent_evaluation") or {}
    evaluation_summary = _evaluation_summary(evaluation)
    warning_values = _warnings(trip, evaluation, warnings)
    memory_context = trip.get("memory_context") or next_payload.get("memory_context") or {}
    planning_brief = trip.get("planning_brief") or next_payload.get("planning_brief") or {}
    agent_trace = trip.get("agent_trace") or {}
    repair_summary = _repair_summary(trip, next_payload)
    frontend_display = {
        "kind": "create_itinerary",
        "title": trip.get("trip_title"),
        "status": trip.get("status"),
        "day_count": len(days),
        "place_count": len(places),
        "summary": trip.get("route_summary") or next_payload.get("summary"),
        "agent_summary": controller_action.concise_decision_summary if controller_action else None,
        "badges": _display_badges(evaluation, memory_context),
    }

    compatibility = {
        "agent_summary": _agent_summary(controller_action, evaluation, repair_summary),
        "understood_constraints": _understood_constraints(planning_brief),
        "repair_summary": repair_summary,
        "replan_attempts": agent_trace.get("agent_loop_iterations") or evaluation.get("iterations"),
        "days": days,
        "places": places,
        "route_legs": route_legs,
        "schedule": schedule,
        "summary": trip.get("route_summary") or "",
        "evaluation_summary": evaluation_summary,
        "warnings": warning_values,
        "memory_used": bool(memory_context.get("long_term") or memory_context.get("preference_summary")),
        "frontend_display": frontend_display,
    }
    next_payload.update(compatibility)
    trip.update(compatibility)
    if controller_action is not None:
        trip["agent_controller"] = controller_action.model_dump(mode="json")
        next_payload["agent_controller"] = controller_action.model_dump(mode="json")
    next_payload["trip"] = trip
    return next_payload


def compose_modify_response(
    trip: dict[str, Any],
    *,
    changed_items: list[dict[str, Any]] | None = None,
    preserved_items: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    next_trip = dict(trip)
    days = list(next_trip.get("itinerary_days") or [])
    evaluation = next_trip.get("agent_evaluation") or {}
    planning_brief = next_trip.get("planning_brief") or {}
    repair_summary = _repair_summary(next_trip, next_trip)
    next_trip.setdefault("agent_summary", _agent_summary(None, evaluation, repair_summary))
    next_trip.setdefault("understood_constraints", _understood_constraints(planning_brief))
    next_trip.setdefault("repair_summary", repair_summary)
    next_trip.setdefault("replan_attempts", (next_trip.get("agent_trace") or {}).get("agent_loop_iterations"))
    next_trip.setdefault("updated_itinerary", days)
    next_trip.setdefault("changed_items", changed_items or [])
    next_trip.setdefault("preserved_items", preserved_items or [])
    next_trip.setdefault("evaluation_summary", _evaluation_summary(evaluation))
    next_trip.setdefault("route_summary", next_trip.get("route_summary"))
    next_trip.setdefault("warnings", _warnings(next_trip, evaluation, warnings))
    next_trip.setdefault(
        "frontend_display",
        {
            "kind": "modify_itinerary",
            "title": next_trip.get("trip_title"),
            "status": next_trip.get("status"),
            "day_count": len(days),
            "place_count": len(_extract_places(days)),
        },
    )
    return next_trip


def compose_hotel_response(
    result: dict[str, Any],
    *,
    trip_id: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    hotels = list(result.get("hotels") or [])
    next_result = dict(result)
    next_result.setdefault("trip_id", trip_id)
    next_result.setdefault("hotel_candidates", hotels)
    next_result.setdefault("ranking_reason", _candidate_reasons(hotels))
    next_result.setdefault("ranking_summary", _ranking_summary(hotels))
    next_result.setdefault("agent_summary", _search_agent_summary("hotel_search", hotels, warnings))
    next_result.setdefault("search_conditions", result.get("parsedParams") or {})
    next_result.setdefault("warnings", warnings or [])
    next_result.setdefault(
        "frontend_display",
        {"kind": "hotel_search", "candidate_count": len(hotels), "trip_id": trip_id},
    )
    return next_result


def compose_flight_response(
    result: dict[str, Any],
    *,
    trip_id: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    flights = list(result.get("flights") or [])
    next_result = dict(result)
    next_result.setdefault("trip_id", trip_id)
    next_result.setdefault("flight_candidates", flights)
    next_result.setdefault("ranking_reason", _candidate_reasons(flights))
    next_result.setdefault("ranking_summary", _ranking_summary(flights))
    next_result.setdefault("agent_summary", _search_agent_summary("flight_search", flights, warnings))
    next_result.setdefault("search_conditions", result.get("parsedParams") or {})
    next_result.setdefault("warnings", warnings or [])
    next_result.setdefault(
        "frontend_display",
        {"kind": "flight_search", "candidate_count": len(flights), "trip_id": trip_id},
    )
    return next_result


def _extract_places(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    places: list[dict[str, Any]] = []
    seen: set[str] = set()
    for day in days:
        for item in day.get("items") or []:
            place = item.get("place") if isinstance(item, dict) else None
            if not isinstance(place, dict):
                continue
            key = str(place.get("place_id") or place.get("name") or item.get("title") or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            places.append(dict(place))
    return places


def _extract_route_legs(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    legs: list[dict[str, Any]] = []
    for day in days:
        for item in day.get("items") or []:
            leg = item.get("route_to_next") if isinstance(item, dict) else None
            if isinstance(leg, dict):
                legs.append({"day_number": day.get("day_number"), "from": item.get("title"), **leg})
    return legs


def _extract_schedule(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    schedule: list[dict[str, Any]] = []
    for day in days:
        for item in day.get("items") or []:
            if not isinstance(item, dict) or item.get("itemKind") == "gap":
                continue
            schedule.append(
                {
                    "day_number": day.get("day_number"),
                    "time_slot": item.get("time_slot"),
                    "start_time": item.get("start_time"),
                    "end_time": item.get("end_time"),
                    "title": item.get("title"),
                }
            )
    return schedule


def _evaluation_summary(evaluation: Any) -> list[str]:
    if not isinstance(evaluation, dict):
        return []
    values = evaluation.get("summary") or evaluation.get("feedback") or evaluation.get("natural_language_feedback") or []
    if isinstance(values, str):
        return [values]
    return [str(value) for value in values if str(value).strip()][:8]


def _warnings(trip: dict[str, Any], evaluation: Any, extra: list[str] | None) -> list[str]:
    values: list[str] = [str(value) for value in (extra or []) if str(value).strip()]
    values.extend(str(value) for value in trip.get("agent_warnings") or [] if str(value).strip())
    if isinstance(evaluation, dict):
        for warning in evaluation.get("warnings") or []:
            if isinstance(warning, dict):
                values.append(str(warning.get("message") or warning.get("reason") or warning.get("target") or warning))
            else:
                values.append(str(warning))
    return list(dict.fromkeys(values))[:12]


def _display_badges(evaluation: Any, memory_context: dict[str, Any]) -> list[str]:
    badges = []
    if isinstance(evaluation, dict) and evaluation.get("passed"):
        badges.append("Agent reviewed")
    if memory_context.get("long_term") or memory_context.get("preference_summary"):
        badges.append("Memory used")
    if isinstance(evaluation, dict) and evaluation.get("hard_failures") == []:
        badges.append("Hard constraints passed")
    return badges


def _candidate_reasons(candidates: list[dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    for candidate in candidates[:5]:
        reason = candidate.get("reason") or candidate.get("ranking_reason")
        if reason:
            reasons.append(str(reason))
    return reasons


def _understood_constraints(planning_brief: Any) -> dict[str, Any]:
    if not isinstance(planning_brief, dict):
        return {}
    keys = (
        "destination",
        "trip_days",
        "must_include",
        "must_avoid",
        "preferred_time_slots",
        "pace",
        "travel_style",
        "meal_preference",
        "final_anchor",
        "ordered_anchors",
        "night_view_required",
        "memory_preferences",
    )
    return {key: planning_brief.get(key) for key in keys if planning_brief.get(key) not in (None, [], {})}


def _repair_summary(trip: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    actions = list(trip.get("agent_replanner_actions") or payload.get("_replanner_actions") or [])
    return {
        "attempted": bool(actions),
        "action_count": len(actions),
        "operations": actions[:12],
    }


def _agent_summary(
    controller_action: AgentActionPlan | None,
    evaluation: Any,
    repair_summary: dict[str, Any],
) -> str:
    if controller_action and controller_action.concise_decision_summary:
        lead = controller_action.concise_decision_summary
    else:
        lead = "Agent reviewed the itinerary request."
    if isinstance(evaluation, dict) and evaluation.get("passed"):
        lead += " Evaluation passed."
    elif isinstance(evaluation, dict):
        lead += " Evaluation found issues and returned review notes."
    if repair_summary.get("attempted"):
        lead += f" Replanner applied {repair_summary.get('action_count')} repair operation(s)."
    return lead


def _ranking_summary(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    top = candidates[0] if candidates else {}
    return {
        "candidate_count": len(candidates),
        "top_candidate": top.get("name") or top.get("id") or top.get("hotelId"),
        "top_score": top.get("overall_score") or top.get("score"),
        "top_reason": top.get("ranking_reason") or top.get("reason"),
    }


def _search_agent_summary(kind: str, candidates: list[dict[str, Any]], warnings: list[str] | None) -> str:
    label = "Hotel" if kind == "hotel_search" else "Flight"
    if candidates:
        top = candidates[0]
        name = top.get("name") or top.get("id") or top.get("hotelId") or "top candidate"
        return f"{label} agent ranked {len(candidates)} API-backed candidate(s). Top pick: {name}."
    if warnings:
        return f"{label} agent could not rank candidates because warnings were returned."
    return f"{label} agent found no API-backed candidates for the current conditions."
