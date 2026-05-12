from __future__ import annotations

from typing import Any

from parser_api.mcp_servers.common import build_server
from parser_api.services.place_catalog import (
    apply_modifications,
    build_itinerary,
    optimize_route,
    recommend_places,
    resolve_place,
    search_places,
)

SERVICE_NAME = "place-catalog-service"
mcp = build_server(SERVICE_NAME)


def generate_itinerary(payload: dict[str, Any]) -> dict[str, Any]:
    return build_itinerary(payload)


def update_itinerary(
    *,
    plan_payload: dict[str, Any],
    modify_payload: dict[str, Any],
    existing_itinerary_days: list[dict[str, Any]] | None = None,
    existing_route_summary: str | None = None,
) -> dict[str, Any]:
    return apply_modifications(
        plan_payload=plan_payload,
        modify_payload=modify_payload,
        existing_itinerary_days=existing_itinerary_days,
        existing_route_summary=existing_route_summary,
    )


def get_recommendations(
    *,
    venue_type: str,
    themes: list[str],
    count: int,
    must_include: list[str] | None = None,
    must_avoid: list[str] | None = None,
    anchor_name: str | None = None,
) -> list[dict[str, Any]]:
    return recommend_places(
        venue_type=venue_type,
        themes=themes,
        count=count,
        must_include=must_include,
        must_avoid=must_avoid,
        anchor_name=anchor_name,
    )


def get_optimized_route(
    *,
    route_points: list[str],
    trip_route_points: list[str] | None = None,
) -> dict[str, Any]:
    return optimize_route(
        route_points=route_points,
        trip_route_points=trip_route_points,
    )


@mcp.tool
def build_itinerary_tool(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    return generate_itinerary(payload)


@mcp.tool
def apply_modifications_tool(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    return update_itinerary(
        plan_payload=dict(payload.get("plan_payload") or {}),
        modify_payload=dict(payload.get("modify_payload") or {}),
        existing_itinerary_days=list(payload.get("existing_itinerary_days") or []),
        existing_route_summary=payload.get("existing_route_summary"),
    )


@mcp.tool
def recommend_places_tool(payload: dict[str, Any], context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    del context
    return get_recommendations(
        venue_type=str(payload.get("venue_type") or "attraction"),
        themes=list(payload.get("themes") or []),
        count=int(payload.get("count") or 3),
        must_include=list(payload.get("must_include") or []),
        must_avoid=list(payload.get("must_avoid") or []),
        anchor_name=payload.get("anchor_name"),
    )


@mcp.tool
def optimize_route_tool(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    return get_optimized_route(
        route_points=list(payload.get("route_points") or []),
        trip_route_points=list(payload.get("trip_route_points") or []),
    )


@mcp.tool
def search_places_tool(payload: dict[str, Any], context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    del context
    return search_places(
        search=str(payload.get("search") or ""),
        category=str(payload.get("category") or ""),
        sort=str(payload.get("sort") or ""),
        limit=int(payload.get("limit") or 60),
    )


@mcp.tool
def resolve_place_tool(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    del context
    return resolve_place(payload.get("query"))


if __name__ == "__main__":
    mcp.run()
