import re
from typing import Optional

from parser_api.intents import Intent
from parser_api.parsers.create_plan.preferences import (
    _extract_place_preferences,
    _extract_themes,
)
from parser_api.parsers.hotel_search.parser import _extract_area_and_landmark
from parser_api.parsers.llm import augment_payload_with_llm
from parser_api.parsers.workflow.shared_context.parser import parse_shared_context
from parser_api.schemas import Clarify, RecommendVenuePayload

_PLAIN_THEME_TOKEN_MAP = {
    "shopping": ("쇼핑", "shopping"),
    "night_view": ("야경", "nightview", "night-view"),
    "cafe": ("카페", "cafe"),
    "foodie": ("맛집", "식당", "레스토랑", "restaurant"),
}


def _infer_venue_type(text: str) -> str:
    lowered = text.lower()
    has_restaurant = any(token in lowered for token in ("맛집", "식당", "레스토랑", "restaurant"))
    has_cafe = any(token in lowered for token in ("카페", "cafe"))
    has_attraction = any(token in lowered for token in ("명소", "관광지", "볼거리", "가볼만한곳", "attraction", "landmark"))

    types = [has_restaurant, has_cafe, has_attraction]
    if sum(bool(value) for value in types) >= 2:
        return "mixed"
    if has_restaurant:
        return "restaurant"
    if has_cafe:
        return "cafe"
    return "attraction"


def _extract_count(text: str) -> int:
    compact = text.replace(" ", "")
    match = re.search(r"(\d+)(?:곳|군데|개)?(?:만)?(?:추천|알려)", compact)
    if match:
        return max(1, min(20, int(match.group(1))))
    return 3


def _extract_recommend_themes(message: str) -> list[str]:
    compact = message.replace(" ", "").lower()
    themes = list(_extract_themes(message))
    for theme, tokens in _PLAIN_THEME_TOKEN_MAP.items():
        if theme not in themes and any(token in compact for token in tokens):
            themes.append(theme)
    return themes


class RecommendVenueParser:
    intent = Intent.RECOMMEND_VENUE

    def parse(self, message: str, context: Optional[dict] = None) -> RecommendVenuePayload:
        shared = parse_shared_context(message, context)

        payload = RecommendVenuePayload()
        payload.venue_type = _infer_venue_type(message.replace(" ", "").lower())
        payload.destination = shared.destination
        payload.area, payload.landmark = _extract_area_and_landmark(message)
        payload.party = shared.party
        payload.budget = shared.budget
        payload.themes = _extract_recommend_themes(message)
        payload.must_include, payload.must_avoid = _extract_place_preferences(message)
        payload.count = _extract_count(message)
        payload = augment_payload_with_llm(payload, message, context)

        missing_fields: list[str] = []
        if payload.destination.city is None:
            missing_fields.append("destination")

        payload.clarify = Clarify(
            needed=bool(missing_fields),
            missing_fields=missing_fields,
        )
        return payload


RECOMMEND_VENUE_PARSER = RecommendVenueParser()


def parse_recommend_venue(message: str, context: Optional[dict] = None) -> RecommendVenuePayload:
    return RECOMMEND_VENUE_PARSER.parse(message, context)
