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


def _apply_rule_overrides(plan: CreatePlanPayload, message: str) -> CreatePlanPayload:
    plan.intent = Intent.CREATE_PLAN.value
    plan.destination.city = "Paris"
    plan.destination.country = "FR"
    compact = message.replace(" ", "")

    days, start_iso, end_iso, source = _extract_days(message)
    plan.dates.days = max(1, days) if isinstance(days, int) else None
    plan.dates.source = source
    plan.dates.start_date = start_iso
    plan.dates.end_date = end_iso

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
    elif any(token in message for token in ("빡세게", "타이트", "빽빽")):
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

    missing_fields = []
    if plan.dates.days is None or plan.dates.source == "missing":
        missing_fields.append("dates.days")
    plan.clarify.missing_fields = missing_fields
    plan.clarify.needed = len(missing_fields) > 0

    return plan
