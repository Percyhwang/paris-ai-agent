import re
from typing import Optional

from parser_api.intents import Intent
from parser_api.parsers.common.constants import TRANSIT_MODE_TOKENS, WALK_MODE_TOKENS
from parser_api.parsers.modify_plan.constants import KNOWN_PLACES
from parser_api.parsers.modify_plan.inference import _extract_target_day
from parser_api.parsers.llm import augment_payload_with_llm
from parser_api.parsers.workflow.shared_context.parser import (
    _apply_location,
    _location_from_token,
    parse_shared_context,
)
from parser_api.schemas import Clarify, LocationRef, OptimizeRoutePayload, RoutePoint


def _extract_route_points(message: str) -> list[RoutePoint]:
    points: list[RoutePoint] = []
    for place in KNOWN_PLACES:
        if place in message:
            points.append(RoutePoint(name=place))
    return points


def _extract_start_end_locations(message: str) -> tuple[LocationRef, LocationRef]:
    start = LocationRef()
    end = LocationRef()
    compact = message.replace(" ", "")

    start_matches = list(
        re.finditer(r"(?:^|[,\s])([A-Za-z0-9가-힣_-]+)에서\s*(?:시작|출발)", message)
    )
    if start_matches:
        token = start_matches[-1].group(1)
        if token in ("인천", "서울", "파리", "ICN", "GMP", "CDG", "ORY"):
            _apply_location(start, _location_from_token(token.lower() if token.isascii() else token))
        else:
            start.landmark = token
    else:
        start_match = re.search(r"([A-Za-z0-9가-힣_-]+)에서(?:시작|출발)", compact)
        if start_match:
            token = start_match.group(1)
            if token in ("인천", "서울", "파리", "ICN", "GMP", "CDG", "ORY"):
                _apply_location(start, _location_from_token(token.lower() if token.isascii() else token))
            else:
                start.landmark = token

    end_matches = list(
        re.finditer(r"(?:^|[,\s])([A-Za-z0-9가-힣_-]+)(?:로|에서)\s*(?:끝|마무리|도착)", message)
    )
    if end_matches:
        token = end_matches[-1].group(1)
        if token in ("인천", "서울", "파리", "ICN", "GMP", "CDG", "ORY"):
            _apply_location(end, _location_from_token(token.lower() if token.isascii() else token))
        else:
            end.landmark = token
        return start, end

    end_matches = list(
        re.finditer(r"([A-Za-z0-9가-힣_-]+)(?:로|에서)(?:끝|마무리|도착)", compact)
    )
    if end_matches:
        token = end_matches[-1].group(1)
        if token in ("인천", "서울", "파리", "ICN", "GMP", "CDG", "ORY"):
            _apply_location(end, _location_from_token(token.lower() if token.isascii() else token))
        else:
            end.landmark = token

    return start, end


def _infer_travel_mode(text: str) -> str:
    if any(token in text for token in WALK_MODE_TOKENS):
        return "walk"
    if any(token in text for token in TRANSIT_MODE_TOKENS):
        return "transit"
    return "both"


def _infer_optimize_goal(text: str) -> str:
    if any(token in text for token in ("도보최소", "걷기최소", "walkleast")):
        return "min_walking"
    if any(token in text for token in ("거리최소", "최단거리")):
        return "min_distance"
    if "환승" in text:
        return "min_transfers"
    return "min_time"


class OptimizeRouteParser:
    intent = Intent.OPTIMIZE_ROUTE

    def parse(self, message: str, context: Optional[dict] = None) -> OptimizeRoutePayload:
        shared = parse_shared_context(message, context)
        compact = message.replace(" ", "").lower()

        payload = OptimizeRoutePayload()
        payload.trip_id = shared.trip_id
        payload.target_day = _extract_target_day(message.replace(" ", ""))
        payload.route_points = _extract_route_points(message)
        payload.start_location, payload.end_location = _extract_start_end_locations(message)
        payload.travel_mode = _infer_travel_mode(compact)
        payload.optimize = _infer_optimize_goal(compact)
        payload = augment_payload_with_llm(payload, message, context)

        missing_fields: list[str] = []
        if not payload.route_points and payload.trip_id is None:
            missing_fields.append("route_points")

        payload.clarify = Clarify(
            needed=bool(missing_fields),
            missing_fields=missing_fields,
        )
        return payload


OPTIMIZE_ROUTE_PARSER = OptimizeRouteParser()


def parse_optimize_route(message: str, context: Optional[dict] = None) -> OptimizeRoutePayload:
    return OPTIMIZE_ROUTE_PARSER.parse(message, context)
