from parser_api.parsers.common.constants import (
    FAST_PACE_TOKENS,
    SLOW_PACE_TOKENS,
    TRANSIT_MODE_TOKENS,
    WALK_MODE_TOKENS,
)
from parser_api.parsers.create_plan.preferences import (
    _extract_place_preferences,
    _extract_themes,
)
from parser_api.parsers.hotel_search.parser import _extract_area_and_landmark, _extract_star_rating
from parser_api.parsers.workflow.shared_context.parser import parse_shared_context
from parser_api.schemas import UserProfilePreferences

_FOOD_PREFERENCE_TOKEN_MAP = {
    "brunch": ("브런치",),
    "dessert": ("디저트", "케이크", "마카롱"),
    "bakery": ("빵", "베이커리"),
    "coffee": ("커피",),
    "wine": ("와인",),
    "michelin": ("미슐랭",),
    "korean_food": ("한식",),
}

_AVOID_TOKEN_MAP = {
    "museum": ("박물관싫어", "미술관싫어", "전시싫어"),
    "shopping": ("쇼핑싫어", "쇼핑안좋아"),
    "long_walk": ("많이걷기싫어", "많이걷는거싫어", "많이걷는건싫어", "걷는거싫어", "도보싫어", "longwalk"),
    "crowded": ("사람많은곳싫어", "붐비는곳싫어"),
}
_PLAIN_THEME_TOKEN_MAP = {
    "foodie": ("맛집", "식당", "레스토랑", "restaurant"),
    "cafe": ("카페", "cafe"),
    "night_view": ("야경", "nightview", "night-view"),
    "shopping": ("쇼핑", "shopping"),
    "museum": ("미술관", "박물관", "전시", "museum"),
    "history": ("역사", "유적"),
    "culture": ("문화", "공연", "오페라", "뮤지컬", "culture"),
    "local": ("로컬", "현지감성"),
    "landmark": ("명소", "관광지"),
    "nature": ("공원", "산책", "피크닉"),
}


def _infer_optional_pace_level(text: str) -> str | None:
    if any(token in text for token in SLOW_PACE_TOKENS):
        return "slow"
    if any(token in text for token in FAST_PACE_TOKENS):
        return "fast"
    if "보통" in text or "적당히" in text:
        return "normal"
    return None


def _infer_optional_travel_mode(text: str) -> str | None:
    if any(token in text for token in WALK_MODE_TOKENS):
        return "walk"
    if any(token in text for token in TRANSIT_MODE_TOKENS):
        return "transit"
    if any(token in text for token in ("둘다", "둘 다", "상관없어")):
        return "both"
    return None


def _infer_optional_budget_mode(text: str, shared_budget_mode: str) -> str | None:
    if any(token in text for token in ("가성비", "저렴", "아껴", "알뜰")):
        return "save"
    if any(token in text for token in ("럭셔리", "고급", "프리미엄", "호화")):
        return "flex"
    if "보통예산" in text or "적당한예산" in text:
        return "normal"
    if shared_budget_mode != "normal":
        return shared_budget_mode
    return None


def _extract_food_preferences(text: str) -> list[str]:
    found: list[str] = []
    for preference, tokens in _FOOD_PREFERENCE_TOKEN_MAP.items():
        if any(token in text for token in tokens):
            found.append(preference)
    return list(dict.fromkeys(found))


def _extract_avoid_preferences(text: str, places_to_avoid: list[str]) -> list[str]:
    found = list(places_to_avoid)
    for preference, tokens in _AVOID_TOKEN_MAP.items():
        if any(token in text for token in tokens):
            found.append(preference)
    return list(dict.fromkeys(found))


def _extract_preferred_themes(message: str) -> list[str]:
    compact = message.replace(" ", "").lower()
    themes = list(_extract_themes(message))
    for theme, tokens in _PLAIN_THEME_TOKEN_MAP.items():
        if theme not in themes and any(token in compact for token in tokens):
            themes.append(theme)
    return themes


def build_profile_preferences(message: str, context: dict | None = None) -> UserProfilePreferences:
    shared = parse_shared_context(message, context)
    compact = message.replace(" ", "").lower()
    area, landmark = _extract_area_and_landmark(message)
    _, must_avoid = _extract_place_preferences(message)

    profile = UserProfilePreferences()
    if shared.party.trip_style != "unknown":
        profile.trip_style = shared.party.trip_style
    profile.pace_level = _infer_optional_pace_level(compact)
    profile.budget_mode = _infer_optional_budget_mode(compact, shared.budget.budget_mode)
    profile.travel_mode = _infer_optional_travel_mode(compact)
    profile.preferred_themes = _extract_preferred_themes(message)
    if area is not None:
        profile.preferred_areas = [area]
    if landmark is not None:
        profile.preferred_landmarks = [landmark]
    profile.accommodation_star_rating = _extract_star_rating(message)
    profile.food_preferences = _extract_food_preferences(compact)
    profile.avoid_preferences = _extract_avoid_preferences(compact, must_avoid)
    return profile
