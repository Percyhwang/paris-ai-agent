from __future__ import annotations

import logging
import math
from typing import Any, Literal

import httpx

from app.core.config import settings
from app.services.place_repository_service import distance_meters

logger = logging.getLogger(__name__)

GOOGLE_ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
GOOGLE_FIELD_MASK = ",".join(
    [
        "routes.duration",
        "routes.distanceMeters",
        "routes.localizedValues",
        "routes.legs.steps.distanceMeters",
        "routes.legs.steps.staticDuration",
        "routes.legs.steps.navigationInstruction.instructions",
        "routes.legs.steps.localizedValues",
        "routes.legs.steps.travelMode",
        "routes.legs.steps.transitDetails.stopDetails",
        "routes.legs.steps.transitDetails.headsign",
        "routes.legs.steps.transitDetails.stopCount",
        "routes.legs.steps.transitDetails.tripShortText",
        "routes.legs.steps.transitDetails.transitLine.name",
        "routes.legs.steps.transitDetails.transitLine.nameShort",
        "routes.legs.steps.transitDetails.transitLine.vehicle",
    ]
)

RouteMode = Literal["walk", "transit", "mixed"]


async def get_route_leg(
    origin: dict[str, float],
    destination: dict[str, float],
    requested_mode: RouteMode,
    language: str,
) -> dict[str, Any]:
    mode = _resolve_mode(origin, destination, requested_mode)
    if settings.google_routes_api_key:
        try:
            return await _google_route_leg(origin, destination, mode, language)
        except Exception as exc:
            logger.info("Google Routes lookup failed; using fallback route estimate: %s", exc)

    return fallback_route_leg(origin, destination, mode, language)


def fallback_route_leg(
    origin: dict[str, float],
    destination: dict[str, float],
    mode: Literal["walk", "transit"],
    language: str,
) -> dict[str, Any]:
    distance = distance_meters(origin, destination)
    if mode == "walk":
        duration_seconds = max(3 * 60, round((distance / 1000) / 4.5 * 3600))
        summary = _copy(language, f"Walk about {_format_duration(duration_seconds, language)}.", f"도보 약 {_format_duration(duration_seconds, language)} 이동")
    else:
        duration_seconds = max(8 * 60, round((distance / 1000) / 18 * 3600) + 6 * 60)
        summary = _copy(
            language,
            f"Transit estimate about {_format_duration(duration_seconds, language)}.",
            f"대중교통 예상 약 {_format_duration(duration_seconds, language)} 이동",
        )

    return {
        "mode": mode,
        "summary": summary,
        "distance_meters": distance,
        "duration_seconds": duration_seconds,
        "duration_text": _format_duration(duration_seconds, language),
        "steps": [_fallback_step(mode, duration_seconds, language)],
        "transit_lines": [],
        "fallback": True,
    }


async def _google_route_leg(
    origin: dict[str, float],
    destination: dict[str, float],
    mode: Literal["walk", "transit"],
    language: str,
) -> dict[str, Any]:
    body = {
        "origin": {"location": {"latLng": {"latitude": origin["lat"], "longitude": origin["lng"]}}},
        "destination": {"location": {"latLng": {"latitude": destination["lat"], "longitude": destination["lng"]}}},
        "travelMode": "WALK" if mode == "walk" else "TRANSIT",
        "languageCode": "ko" if language == "ko" else "en",
        "units": "METRIC",
        "computeAlternativeRoutes": False,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_routes_api_key or "",
        "X-Goog-FieldMask": GOOGLE_FIELD_MASK,
    }
    async with httpx.AsyncClient(timeout=12) as client:
        response = await client.post(GOOGLE_ROUTES_URL, json=body, headers=headers)
        response.raise_for_status()

    data = response.json()
    route = (data.get("routes") or [{}])[0]
    if not route:
        return fallback_route_leg(origin, destination, mode, language)

    distance = int(route.get("distanceMeters") or distance_meters(origin, destination))
    duration_seconds = _duration_to_seconds(route.get("duration")) or fallback_route_leg(origin, destination, mode, language)[
        "duration_seconds"
    ]
    duration_text = _localized_text(route, "duration") or _format_duration(duration_seconds, language)
    steps = _parse_steps(route, language)
    transit_lines = _transit_lines_from_steps(steps)
    summary = _google_summary(mode, duration_text, distance, transit_lines, language)
    return {
        "mode": mode,
        "summary": summary,
        "distance_meters": distance,
        "duration_seconds": duration_seconds,
        "duration_text": duration_text,
        "steps": steps,
        "transit_lines": transit_lines,
        "fallback": False,
    }


def _parse_steps(route: dict[str, Any], language: str) -> list[dict[str, Any]]:
    parsed_steps: list[dict[str, Any]] = []
    for leg in route.get("legs") or []:
        for step in leg.get("steps") or []:
            transit = step.get("transitDetails") or {}
            line = transit.get("transitLine") or {}
            vehicle = line.get("vehicle") or {}
            vehicle_name = vehicle.get("name") if isinstance(vehicle.get("name"), dict) else {}
            stop_details = transit.get("stopDetails") or {}
            departure_stop = stop_details.get("departureStop") or {}
            arrival_stop = stop_details.get("arrivalStop") or {}
            travel_mode = str(step.get("travelMode") or "").lower()
            instruction = _step_instruction(step, line, transit, language)
            if not instruction:
                continue
            parsed_steps.append(
                {
                    "instruction": instruction,
                    "travel_mode": travel_mode or None,
                    "line_name": line.get("name"),
                    "line_short_name": line.get("nameShort"),
                    "vehicle_type": vehicle.get("type") or vehicle_name.get("text"),
                    "departure_stop": departure_stop.get("name"),
                    "arrival_stop": arrival_stop.get("name"),
                    "duration_text": _step_duration_text(step),
                    "stop_count": transit.get("stopCount"),
                }
            )
    return parsed_steps[:8]


def _step_instruction(step: dict[str, Any], line: dict[str, Any], transit: dict[str, Any], language: str) -> str | None:
    navigation = step.get("navigationInstruction") or {}
    instruction = navigation.get("instructions")
    if instruction:
        return str(instruction)

    short_name = line.get("nameShort") or line.get("name")
    stop_details = transit.get("stopDetails") or {}
    departure = (stop_details.get("departureStop") or {}).get("name")
    arrival = (stop_details.get("arrivalStop") or {}).get("name")
    if short_name and departure and arrival:
        if language == "en":
            return f"Take {short_name} from {departure} to {arrival}."
        return f"{departure}에서 {short_name} 탑승 후 {arrival} 하차"
    return None


def _step_duration_text(step: dict[str, Any]) -> str | None:
    localized = step.get("localizedValues") or {}
    duration = localized.get("staticDuration") or localized.get("duration") or {}
    return duration.get("text") if isinstance(duration, dict) else None


def _transit_lines_from_steps(steps: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for step in steps:
        line = step.get("line_short_name") or step.get("line_name")
        if line and line not in lines:
            lines.append(str(line))
    return lines


def _google_summary(
    mode: Literal["walk", "transit"],
    duration_text: str,
    distance: int,
    transit_lines: list[str],
    language: str,
) -> str:
    distance_text = _format_distance(distance)
    if mode == "walk":
        return _copy(language, f"Walk {duration_text} - {distance_text}", f"도보 {duration_text} - {distance_text}")
    if transit_lines:
        lines = ", ".join(transit_lines[:3])
        return _copy(
            language,
            f"Transit {duration_text} - line {lines}",
            f"대중교통 {duration_text} - 노선 {lines}",
        )
    return _copy(language, f"Transit {duration_text} - {distance_text}", f"대중교통 {duration_text} - {distance_text}")


def _resolve_mode(
    origin: dict[str, float],
    destination: dict[str, float],
    requested_mode: RouteMode,
) -> Literal["walk", "transit"]:
    if requested_mode in {"walk", "transit"}:
        return requested_mode
    return "walk" if distance_meters(origin, destination) <= 1200 else "transit"


def _fallback_step(mode: Literal["walk", "transit"], duration_seconds: int, language: str) -> dict[str, Any]:
    if mode == "walk":
        instruction = _copy(language, "Walk to the next stop.", "다음 장소까지 도보 이동")
    else:
        instruction = _copy(language, "Use nearby metro or bus service for this leg.", "가까운 지하철 또는 버스로 다음 장소까지 이동")
    return {"instruction": instruction, "travel_mode": mode, "duration_text": _format_duration(duration_seconds, language)}


def _duration_to_seconds(value: Any) -> int | None:
    if not isinstance(value, str) or not value.endswith("s"):
        return None
    try:
        return max(1, math.ceil(float(value[:-1])))
    except ValueError:
        return None


def _localized_text(container: dict[str, Any], key: str) -> str | None:
    localized = container.get("localizedValues") or {}
    value = localized.get(key) or {}
    return value.get("text") if isinstance(value, dict) else None


def _format_duration(seconds: int, language: str) -> str:
    minutes = max(1, round(seconds / 60))
    hours, minute_remainder = divmod(minutes, 60)
    if language == "en":
        if hours and minute_remainder:
            return f"{hours} hr {minute_remainder} min"
        if hours:
            return f"{hours} hr"
        return f"{minutes} min"
    if hours and minute_remainder:
        return f"{hours}시간 {minute_remainder}분"
    if hours:
        return f"{hours}시간"
    return f"{minutes}분"


def _format_distance(meters: int) -> str:
    if meters >= 1000:
        return f"{meters / 1000:.1f} km"
    return f"{meters} m"


def _copy(language: str, en: str, ko: str) -> str:
    return en if language == "en" else ko
