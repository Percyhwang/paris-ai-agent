from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.parsers.agent_action_parser import validate_agent_action
from app.parsers.create_plan_parser import parse_create_plan_action
from app.parsers.flight_search_parser import parse_flight_search_action
from app.parsers.hotel_search_parser import parse_hotel_search_action
from app.parsers.modify_plan_parser import parse_modify_plan_action
from app.schemas.agent_action_schema import AgentActionPlan, AgentIntent
from app.schemas.trips import TripAgentModifyRequest, TripGenerateRequest
from app.services.flight_ranker_service import rank_flights_for_trip
from app.services.hotel_ranker_service import rank_hotels_for_trip
from app.services.llm_controller_service import plan_agent_action
from app.services.response_composer_service import (
    compose_create_itinerary_payload,
    compose_flight_response,
    compose_hotel_response,
)
from app.services.trip_state_service import load_trip_state, save_flight_candidates, save_hotel_candidates


CreateExecutor = Callable[[TripGenerateRequest, str, Any | None, str | None], Awaitable[dict[str, Any]]]
ModifyExecutor = Callable[[TripAgentModifyRequest], Awaitable[dict[str, Any]]]
SearchExecutor = Callable[[], Awaitable[dict[str, Any]]]


async def orchestrate_create_itinerary(
    request: TripGenerateRequest,
    *,
    language: str,
    db: Any | None,
    user_id: str | None,
    execute_create: CreateExecutor,
) -> dict[str, Any]:
    controller_action = plan_agent_action(
        request.prompt,
        context={
            "entrypoint": "backend.trips.generate",
            "language": language,
            "style_tags": list(request.style_tags or []),
            "total_days": request.total_days,
        },
    )
    validation = validate_agent_action(controller_action)
    action = validation.action
    if action.intent != AgentIntent.CREATE_ITINERARY:
        action = AgentActionPlan(
            intent=AgentIntent.CREATE_ITINERARY,
            action="create_itinerary",
            arguments={"prompt": request.prompt, "destination": "Paris"},
            confidence=min(action.confidence, 0.6),
            concise_decision_summary="Request was routed to itinerary generation for this endpoint.",
            raw_text=request.prompt,
            source=action.source,
        )
    parsed = parse_create_plan_action(action, fallback_request=request)
    if not parsed.valid:
        action.needs_clarification = True
        action.missing_required_fields = list(parsed.missing_required_fields)

    payload = await execute_create(request, language, db, user_id)
    return compose_create_itinerary_payload(payload, controller_action=action)


async def orchestrate_modify_itinerary(
    request: TripAgentModifyRequest,
    *,
    context: dict[str, Any],
    execute_modify: ModifyExecutor,
) -> dict[str, Any]:
    controller_action = plan_agent_action(request.prompt, context=context)
    validation = validate_agent_action(controller_action)
    action = validation.action
    if action.intent != AgentIntent.MODIFY_ITINERARY:
        action = AgentActionPlan(
            intent=AgentIntent.MODIFY_ITINERARY,
            action="modify_itinerary",
            arguments={"prompt": request.prompt, "target_day": request.target_day},
            confidence=min(action.confidence, 0.6),
            concise_decision_summary="Request was routed to itinerary modification for this endpoint.",
            raw_text=request.prompt,
            source=action.source,
        )
    parse_modify_plan_action(action, fallback_request=request)
    result = await execute_modify(request)
    result["agent_controller"] = action.model_dump(mode="json")
    return result


async def orchestrate_hotel_search(
    *,
    user_request: str,
    trip_id: str | None,
    db: Any | None,
    user_id: str,
    execute_search: SearchExecutor,
) -> dict[str, Any]:
    action = plan_agent_action(
        user_request,
        context={"entrypoint": "backend.hotels", "trip_id": trip_id},
    )
    validation = validate_agent_action(action)
    action = validation.action
    if action.intent != AgentIntent.SEARCH_HOTEL:
        action = AgentActionPlan(
            intent=AgentIntent.SEARCH_HOTEL,
            action="search_hotel",
            arguments={"query": user_request, "destination": "Paris"},
            confidence=min(action.confidence, 0.6),
            concise_decision_summary="Request was routed to hotel search for this endpoint.",
            raw_text=user_request,
            source=action.source,
        )
    parser_result = parse_hotel_search_action(action)
    result = await execute_search()
    trip_state = await load_trip_state(db, user_id=user_id, trip_id=str(trip_id)) if trip_id else None
    search_conditions = dict(result.get("parsedParams") or result.get("search_conditions") or parser_result.normalized_arguments or {})
    ranked_hotels = rank_hotels_for_trip(
        list(result.get("hotels") or []),
        trip_state=trip_state,
        search_conditions=search_conditions,
    )
    result["hotels"] = ranked_hotels
    result["count"] = len(ranked_hotels)
    result["search_conditions"] = search_conditions
    response = compose_hotel_response(result, trip_id=trip_id, warnings=list(parser_result.warnings or []))
    response["agent_controller"] = action.model_dump(mode="json")
    await save_hotel_candidates(
        db,
        user_id=user_id,
        trip_id=trip_id,
        candidates=list(response.get("hotel_candidates") or []),
        search_conditions=dict(response.get("search_conditions") or {}),
    )
    return response


async def orchestrate_flight_search(
    *,
    user_request: str,
    trip_id: str | None,
    db: Any | None,
    user_id: str,
    execute_search: SearchExecutor,
) -> dict[str, Any]:
    action = plan_agent_action(
        user_request,
        context={"entrypoint": "backend.flights", "trip_id": trip_id},
    )
    validation = validate_agent_action(action)
    action = validation.action
    if action.intent != AgentIntent.SEARCH_FLIGHT:
        action = AgentActionPlan(
            intent=AgentIntent.SEARCH_FLIGHT,
            action="search_flight",
            arguments={"query": user_request, "destination": "Paris"},
            confidence=min(action.confidence, 0.6),
            concise_decision_summary="Request was routed to flight search for this endpoint.",
            raw_text=user_request,
            source=action.source,
        )
    parser_result = parse_flight_search_action(action)
    result = await execute_search()
    trip_state = await load_trip_state(db, user_id=user_id, trip_id=str(trip_id)) if trip_id else None
    search_conditions = dict(result.get("parsedParams") or result.get("search_conditions") or parser_result.normalized_arguments or {})
    ranked_flights = rank_flights_for_trip(
        list(result.get("flights") or []),
        trip_state=trip_state,
        search_conditions=search_conditions,
    )
    result["flights"] = ranked_flights
    result["count"] = len(ranked_flights)
    result["search_conditions"] = search_conditions
    response = compose_flight_response(result, trip_id=trip_id, warnings=list(parser_result.warnings or []))
    response["agent_controller"] = action.model_dump(mode="json")
    await save_flight_candidates(
        db,
        user_id=user_id,
        trip_id=trip_id,
        candidates=list(response.get("flight_candidates") or []),
        search_conditions=dict(response.get("search_conditions") or {}),
    )
    return response
