from typing import Optional

from parser_api.intents import Intent
from parser_api.parsers.user_profile.helpers import build_profile_preferences
from parser_api.schemas import Clarify, UserProfilePayload


def _infer_operation(text: str) -> str:
    if any(token in text for token in ("보여", "조회", "불러", "확인")):
        return "retrieve"
    return "update"


def _profile_has_signal(profile: UserProfilePayload | object) -> bool:
    prefs = profile.profile if isinstance(profile, UserProfilePayload) else profile
    return any(
        value
        for value in (
            prefs.trip_style,
            prefs.pace_level,
            prefs.budget_mode,
            prefs.travel_mode,
            prefs.preferred_themes,
            prefs.preferred_areas,
            prefs.preferred_landmarks,
            prefs.accommodation_star_rating,
            prefs.food_preferences,
            prefs.avoid_preferences,
        )
    )


class UserProfileParser:
    intent = Intent.USER_PROFILE

    def parse(self, message: str, context: Optional[dict] = None) -> UserProfilePayload:
        compact = message.replace(" ", "").lower()

        payload = UserProfilePayload()
        payload.operation = _infer_operation(compact)
        payload.profile = build_profile_preferences(message, context)

        missing_fields: list[str] = []
        if payload.operation == "update" and not _profile_has_signal(payload):
            missing_fields.append("profile")

        payload.clarify = Clarify(
            needed=bool(missing_fields),
            missing_fields=missing_fields,
        )
        return payload


USER_PROFILE_PARSER = UserProfileParser()


def parse_user_profile(message: str, context: Optional[dict] = None) -> UserProfilePayload:
    return USER_PROFILE_PARSER.parse(message, context)

