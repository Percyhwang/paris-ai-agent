import re

from parser_api.intents import Intent
from parser_api.parsers.common.constants import (
    INDOOR_TOKENS,
    LOW_WALK_TOKENS,
    RAINY_TOKENS,
    SLOW_PACE_TOKENS,
    TRANSIT_MODE_TOKENS,
    WALK_MODE_TOKENS,
)
from parser_api.parsers.common.extractors import (
    extract_museum_limit,
    extract_slots_in_order,
    extract_walk_limit,
)
from parser_api.parsers.create_plan.constants import (
    FILIAL_THEME_TOKENS,
    ROMANCE_THEME_TOKENS,
)
from parser_api.parsers.create_plan.dates import _extract_days
from parser_api.parsers.create_plan.party import _extract_party
from parser_api.parsers.create_plan.preferences import (
    _extract_place_preferences,
    _extract_themes,
)
from parser_api.schemas import CreatePlanPayload


MEAL_STYLE_TOKENS: dict[str, tuple[str, ...]] = {
    "brunch": ("브런치", "늦은 아침", "늦은아침", "brunch"),
    "cafe": ("카페", "cafe", "coffee"),
    "dessert": ("디저트", "dessert", "케이크", "베이커리", "빵지순례"),
    "bistro": ("비스트로", "bistro", "brasserie"),
    "wine": ("와인", "wine", "bar"),
    "jazz_bar": ("재즈", "재즈바", "jazz", "jazz bar"),
}

STYLE_TAG_THEME_MAP = {
    "museum": "museum",
    "art": "art",
    "night_view": "night_view",
    "shopping": "shopping",
    "park": "nature",
    "nature": "nature",
    "romantic": "romance",
    "local": "local",
    "hidden_gems": "hidden_gems",
    "foodie": "foodie",
    "cafe": "cafe",
    "landmark": "landmark",
}


def _context_style_tags(context: dict | None) -> list[str]:
    raw = (context or {}).get("style_tags")
    if not isinstance(raw, list):
        return []
    return [str(tag).strip().lower() for tag in raw if str(tag).strip()]


def _extract_meal_preferences(message: str) -> list[str]:
    compact = message.replace(" ", "")
    preferences: list[str] = []
    for style, tokens in MEAL_STYLE_TOKENS.items():
        if style == "jazz_bar" and any(token in compact for token in ("재즈바는제외", "재즈바제외", "재즈바빼", "재즈는제외", "재즈제외")):
            continue
        if any(token in message for token in tokens):
            preferences.append(style)
    return list(dict.fromkeys(preferences))


def _merge_unique(values: list[str], extras: list[str]) -> list[str]:
    return list(dict.fromkeys([*values, *extras]))


def _apply_rule_overrides(plan: CreatePlanPayload, message: str, context: dict | None = None) -> CreatePlanPayload:
    plan.intent = Intent.CREATE_PLAN.value
    plan.destination.city = "Paris"
    plan.destination.country = "FR"
    compact = message.replace(" ", "")
    context_tags = _context_style_tags(context)

    days, start_iso, end_iso, source = _extract_days(message)
    context_total_days = (context or {}).get("total_days")
    context_start_date = (context or {}).get("start_date")
    context_end_date = (context or {}).get("end_date")
    plan.dates.days = max(1, days) if isinstance(days, int) else int(context_total_days or 0) or None
    plan.dates.source = source if source != "missing" else ("explicit" if context_start_date or context_end_date else "missing")
    plan.dates.start_date = start_iso or str(context_start_date or "") or None
    plan.dates.end_date = end_iso or str(context_end_date or "") or None

    party = _extract_party(message)
    plan.party.adult = int(party.get("adult", 0))
    plan.party.highschool = int(party.get("highschool", 0))
    plan.party.middleschool = int(party.get("middleschool", 0))
    plan.party.elementary = int(party.get("elementary", 0))
    plan.party.toddler = int(party.get("toddler", 0))
    plan.party.trip_style = str(party.get("trip_style", "unknown"))

    if any(token in compact for token in WALK_MODE_TOKENS):
        plan.mobility.travel_mode = "walk"
    elif any(token in compact for token in TRANSIT_MODE_TOKENS):
        plan.mobility.travel_mode = "transit"
    else:
        plan.mobility.travel_mode = "both"

    if re.search(r"환승(?:은)?(?:최소|적게|줄여)", compact):
        plan.mobility.optimize = "min_transfers"

    walk_limit = extract_walk_limit(message.lower().replace(" ", ""))
    if walk_limit is not None:
        plan.mobility.max_walk_km_per_day = walk_limit
    elif any(token in compact for token in LOW_WALK_TOKENS):
        plan.mobility.max_walk_km_per_day = 5

    if any(token in compact for token in LOW_WALK_TOKENS) and plan.mobility.travel_mode == "both":
        plan.mobility.travel_mode = "transit"

    if "휠체어" in compact:
        plan.mobility.wheelchair = True

    if "유모차" in compact:
        plan.mobility.stroller = True

    if any(token in message for token in SLOW_PACE_TOKENS):
        plan.pace.level = "slow"
    elif "slow" in context_tags:
        plan.pace.level = "slow"
    elif any(token in message for token in ("빡세게", "타이트", "빽빽")):
        plan.pace.level = "fast"
    elif "fast" in context_tags:
        plan.pace.level = "fast"

    if any(token in message for token in ROMANCE_THEME_TOKENS) and "romance" not in plan.preferences.themes:
        plan.preferences.themes.append("romance")
    if any(token in message for token in FILIAL_THEME_TOKENS) and "family" not in plan.preferences.themes:
        plan.preferences.themes.append("family")
    if "가족여행" in compact and "family" not in plan.preferences.themes:
        plan.preferences.themes.append("family")
    if any(token in compact for token in ("기억에남는", "기억남는", "인상깊은", "하이라이트")):
        for theme in ("landmark", "photo"):
            if theme not in plan.preferences.themes:
                plan.preferences.themes.append(theme)

    for theme in _extract_themes(message):
        if theme not in plan.preferences.themes:
            plan.preferences.themes.append(theme)
    for tag in context_tags:
        mapped_theme = STYLE_TAG_THEME_MAP.get(tag)
        if mapped_theme and mapped_theme not in plan.preferences.themes:
            plan.preferences.themes.append(mapped_theme)

    if "cafe" in plan.preferences.themes:
        plan.preferences.weights.cafe = 0.8
        plan.preferences.weights.museum = 0.3
    if "shopping" in plan.preferences.themes:
        plan.preferences.weights.shopping = 0.8
    if "night_view" in plan.preferences.themes:
        plan.preferences.weights.night_view = 0.8
    if "nature" in plan.preferences.themes:
        plan.preferences.weights.park = 0.8
    if "museum" in plan.preferences.themes:
        plan.preferences.weights.museum = max(plan.preferences.weights.museum, 0.85)
    if "art" in plan.preferences.themes:
        plan.preferences.weights.museum = max(plan.preferences.weights.museum, 0.75)

    if "luxury" in plan.preferences.themes:
        plan.budget.budget_mode = "flex"
    if "budget" in plan.preferences.themes:
        plan.budget.budget_mode = "save"
    if "flex" in context_tags or "luxury" in context_tags:
        plan.budget.budget_mode = "flex"
    if "save" in context_tags or "budget" in context_tags:
        plan.budget.budget_mode = "save"
    if any(token in compact for token in ("아끼", "저예산", "무료", "유료입장")):
        plan.budget.budget_mode = "save"

    if any(token in compact for token in INDOOR_TOKENS):
        plan.constraints.indoor_focus = True
    if any(token in compact for token in RAINY_TOKENS):
        plan.constraints.rainy_plan = True

    museum_limit = extract_museum_limit(message.replace(" ", ""))
    if museum_limit is not None:
        plan.constraints.museum_per_day = museum_limit

    must_include, must_avoid = _extract_place_preferences(message)
    if must_include:
        plan.preferences.must_include = must_include
    if must_avoid:
        plan.preferences.must_avoid = must_avoid

    if "walk" in context_tags:
        plan.mobility.travel_mode = "walk"
    elif "transit" in context_tags:
        plan.mobility.travel_mode = "transit"
    elif "both" in context_tags:
        plan.mobility.travel_mode = "both"

    preferred_slots = extract_slots_in_order(compact)
    meal_preference = _extract_meal_preferences(message)
    night_view_required = "night_view" in plan.preferences.themes or "night_view" in context_tags
    if night_view_required:
        plan.preferences.night_view_required = True
        for slot in ("evening", "night"):
            if slot not in preferred_slots:
                preferred_slots.append(slot)
    if any(token in compact for token in ("석양", "선셋", "sunset")) and "evening" not in preferred_slots:
        preferred_slots.append("evening")
    jazz_avoided = any(token in compact for token in ("재즈바는제외", "재즈바제외", "재즈바빼", "재즈는제외", "재즈제외"))
    if any(token in compact for token in ("재즈", "재즈바", "jazz")) and not jazz_avoided:
        for slot in ("evening", "night"):
            if slot not in preferred_slots:
                preferred_slots.append(slot)
        for theme in ("local", "nightlife"):
            if theme not in plan.preferences.themes:
                plan.preferences.themes.append(theme)

    if "slow" in context_tags and not preferred_slots:
        preferred_slots = ["morning", "afternoon", "evening" if night_view_required else "lunch"]

    travel_style = _merge_unique(
        list(plan.preferences.travel_style),
        [
            *context_tags,
            *plan.preferences.themes,
            plan.pace.level,
            plan.mobility.travel_mode,
            plan.budget.budget_mode,
        ],
    )
    plan.preferences.travel_style = [style for style in travel_style if style]
    plan.preferences.preferred_time_slots = [slot for slot in preferred_slots if slot in {"morning", "lunch", "afternoon", "evening", "night"}]
    plan.preferences.meal_preference = _merge_unique(list(plan.preferences.meal_preference), meal_preference)

    missing_fields = []
    if plan.dates.days is None or plan.dates.source == "missing":
        missing_fields.append("dates.days")
    plan.clarify.missing_fields = missing_fields
    plan.clarify.needed = len(missing_fields) > 0

    return plan
