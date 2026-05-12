from typing import Optional

from parser_api.intents import Intent
from parser_api.parsers.user_profile.helpers import build_profile_preferences
from parser_api.schemas import Clarify, TravelStylePayload

_THEME_TO_VENUE_FOCUS = {
    "cafe": "cafe",
    "foodie": "restaurant",
    "museum": "museum",
    "art": "museum",
    "history": "museum",
    "shopping": "shopping",
    "night_view": "night_view",
    "nature": "park",
    "landmark": "attraction",
    "culture": "attraction",
}


def _build_style_tags(profile) -> list[str]:
    tags: list[str] = list(profile.preferred_themes)
    if profile.trip_style:
        tags.append(profile.trip_style)
    if profile.pace_level:
        tags.append(f"{profile.pace_level}_pace")
    if profile.budget_mode:
        tags.append(f"{profile.budget_mode}_budget")
    if profile.travel_mode:
        tags.append(f"{profile.travel_mode}_mobility")
    if profile.accommodation_star_rating:
        tags.append(f"{profile.accommodation_star_rating}_star_stay")
    if profile.food_preferences:
        tags.extend(profile.food_preferences)
    return list(dict.fromkeys(tags))


def _build_venue_focus(profile) -> list[str]:
    focus: list[str] = []
    for theme in profile.preferred_themes:
        mapped = _THEME_TO_VENUE_FOCUS.get(theme)
        if mapped is not None:
            focus.append(mapped)
    if any(token in profile.food_preferences for token in ("brunch", "dessert", "bakery", "coffee", "wine", "michelin", "korean_food")):
        focus.append("restaurant")
    return list(dict.fromkeys(focus))


class TravelStyleParser:
    intent = Intent.TRAVEL_STYLE

    def parse(self, message: str, context: Optional[dict] = None) -> TravelStylePayload:
        profile = build_profile_preferences(message, context)

        payload = TravelStylePayload()
        payload.style_tags = _build_style_tags(profile)
        payload.trip_style = profile.trip_style
        payload.pace_level = profile.pace_level
        payload.budget_mode = profile.budget_mode
        payload.travel_mode = profile.travel_mode
        payload.venue_focus = _build_venue_focus(profile)

        has_signal = any(
            value
            for value in (
                payload.style_tags,
                payload.trip_style,
                payload.pace_level,
                payload.budget_mode,
                payload.travel_mode,
                payload.venue_focus,
            )
        )
        missing_fields = [] if has_signal else ["style_signal"]
        payload.clarify = Clarify(
            needed=bool(missing_fields),
            missing_fields=missing_fields,
        )
        return payload


TRAVEL_STYLE_PARSER = TravelStyleParser()


def parse_travel_style(message: str, context: Optional[dict] = None) -> TravelStylePayload:
    return TRAVEL_STYLE_PARSER.parse(message, context)

