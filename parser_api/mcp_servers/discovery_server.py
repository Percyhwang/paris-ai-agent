from __future__ import annotations

from typing import Any

from parser_api.intents import Intent
from parser_api.mcp_servers.common import build_server, build_tool_response
from parser_api.mcp_servers.place_catalog_server import get_optimized_route, get_recommendations
from parser_api.schemas import (
    EstimateBudgetPayload,
    OptimizeRoutePayload,
    RecommendVenuePayload,
)
from parser_api.services.trip_store import get_trip_state

SERVICE_NAME = "discovery-service"
mcp = build_server(SERVICE_NAME)


def _estimate_budget_total(payload: EstimateBudgetPayload) -> int | None:
    days = payload.dates.days
    travelers = max(1, payload.party.total or 1)
    if days is None:
        return None

    total = 0
    if payload.components.flight:
        total += 700000 * travelers
    if payload.components.hotel:
        nightly = 90000 + (payload.hotel_star_rating or 3) * 30000
        total += nightly * max(1, days - 1)
    if payload.components.food:
        total += 35000 * days * travelers
    if payload.components.transport:
        total += 12000 * days * travelers
    if payload.components.activities:
        total += 25000 * days * travelers
    if payload.components.shopping:
        total += 80000 * travelers
    return total


def _trip_route_points(payload: OptimizeRoutePayload) -> list[str]:
    if not payload.trip_id:
        return []

    state = get_trip_state(payload.trip_id)
    if state is None:
        return []

    itinerary_days = list(state.get("itinerary_days") or [])
    if payload.target_day is not None:
        selected_day = next(
            (
                day
                for day in itinerary_days
                if int(day.get("day_number") or 0) == payload.target_day
            ),
            None,
        )
        if selected_day is not None:
            return [
                str(((item.get("place") or {}).get("name")) or item.get("title") or "")
                for item in selected_day.get("items", [])
                if ((item.get("place") or {}).get("name")) or item.get("title")
            ]

    if itinerary_days:
        first_day = itinerary_days[0]
        return [
            str(((item.get("place") or {}).get("name")) or item.get("title") or "")
            for item in first_day.get("items", [])
            if ((item.get("place") or {}).get("name")) or item.get("title")
        ]

    return list(state.get("selected_places") or [])


def _build_route_summary(payload: OptimizeRoutePayload) -> dict[str, Any]:
    requested_points = [point.name for point in payload.route_points]
    optimized = get_optimized_route(
        route_points=requested_points,
        trip_route_points=_trip_route_points(payload),
    )
    optimized["travel_mode"] = payload.travel_mode
    optimized["optimize"] = payload.optimize
    optimized["source"] = "trip_state" if not requested_points and payload.trip_id else "request"
    return optimized


def _build_recommendations(payload: RecommendVenuePayload) -> list[dict[str, Any]]:
    anchor_name = payload.landmark or payload.area
    return get_recommendations(
        venue_type=payload.venue_type,
        themes=list(payload.themes),
        count=payload.count,
        must_include=list(payload.must_include),
        must_avoid=list(payload.must_avoid),
        anchor_name=anchor_name,
    )


@mcp.tool
def estimate_budget(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    validated = EstimateBudgetPayload.model_validate(payload)
    estimate_total = _estimate_budget_total(validated)
    return build_tool_response(
        intent=Intent.ESTIMATE_BUDGET,
        data_key="budget_estimate",
        payload_dict=validated.model_dump(),
        service=SERVICE_NAME,
        tool="estimate_budget",
        payload_extras={
            "estimate_total": estimate_total,
            "estimate_currency": validated.budget.currency,
        },
    )


@mcp.tool
def optimize_route(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    validated = OptimizeRoutePayload.model_validate(payload)
    return build_tool_response(
        intent=Intent.OPTIMIZE_ROUTE,
        data_key="route_optimization",
        payload_dict=validated.model_dump(),
        service=SERVICE_NAME,
        tool="optimize_route",
        trip_id=validated.trip_id or "",
        payload_extras=_build_route_summary(validated),
    )


@mcp.tool
def recommend_venue(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    validated = RecommendVenuePayload.model_validate(payload)
    return build_tool_response(
        intent=Intent.RECOMMEND_VENUE,
        data_key="venue_recommendation",
        payload_dict=validated.model_dump(),
        service=SERVICE_NAME,
        tool="recommend_venue",
        payload_extras={
            "recommendations": _build_recommendations(validated),
        },
    )


if __name__ == "__main__":
    mcp.run()
