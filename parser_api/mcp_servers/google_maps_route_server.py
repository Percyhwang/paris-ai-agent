from __future__ import annotations

from typing import Any
from urllib.parse import quote

from parser_api.intents import Intent
from parser_api.mcp_servers.common import build_server, build_tool_response

mcp = build_server("google-maps-route")


def _coordinates(item: dict[str, Any]) -> dict[str, float] | None:
    coordinates = (item.get("place") or {}).get("coordinates")
    if not isinstance(coordinates, dict):
        return None
    lat = coordinates.get("lat")
    lng = coordinates.get("lng")
    if lat is None or lng is None:
        return None
    return {"lat": float(lat), "lng": float(lng)}


def _google_maps_route_url(points: list[dict[str, Any]]) -> str:
    if len(points) < 2:
        if points:
            coordinates = points[0]["coordinates"]
            return f"https://www.google.com/maps/search/?api=1&query={coordinates['lat']},{coordinates['lng']}"
        return "https://www.google.com/maps"
    origin = points[0]["coordinates"]
    destination = points[-1]["coordinates"]
    waypoints = "|".join(f"{point['coordinates']['lat']},{point['coordinates']['lng']}" for point in points[1:-1])
    url = (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={origin['lat']},{origin['lng']}"
        f"&destination={destination['lat']},{destination['lng']}"
        "&travelmode=transit"
    )
    if waypoints:
        url += f"&waypoints={quote(waypoints, safe='|,')}"
    return url


@mcp.tool
def build_day_route_map(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    day = payload.get("day") if isinstance(payload.get("day"), dict) else payload
    points: list[dict[str, Any]] = []
    for item in day.get("items") or []:
        if not isinstance(item, dict):
            continue
        coordinates = _coordinates(item)
        if not coordinates:
            continue
        points.append(
            {
                "name": (item.get("place") or {}).get("name") or item.get("title"),
                "coordinates": coordinates,
                "time_slot": item.get("time_slot"),
                "start_time": item.get("start_time"),
            }
        )

    return build_tool_response(
        intent=Intent.OPTIMIZE_ROUTE,
        data_key="map_route",
        payload_dict={
            "day_number": day.get("day_number"),
            "points": points,
            "google_maps_url": _google_maps_route_url(points),
        },
        service="google_maps_route",
        tool="build_day_route_map",
        trip_id=str(payload.get("trip_id") or ""),
    )
