import re
from typing import Any, Optional

from parser_api.parsers.common.constants import (
    INDOOR_TOKENS,
    LOW_WALK_TOKENS,
    RAINY_TOKENS,
    TRANSIT_MODE_TOKENS,
    WALK_MODE_TOKENS,
)
from parser_api.parsers.common.extractors import (
    extract_museum_limit,
    extract_walk_limit,
)


def _extract_constraint_patch(text: str) -> Optional[dict[str, Any]]:
    patch: dict[str, Any] = {}
    if any(token in text for token in INDOOR_TOKENS):
        patch["indoor_focus"] = True
    if any(token in text for token in RAINY_TOKENS):
        patch["rainy_plan"] = True

    museum_limit = extract_museum_limit(text)
    if museum_limit is not None:
        patch["museum_per_day"] = museum_limit

    return patch or None


def _extract_mobility_patch(text: str) -> Optional[dict[str, Any]]:
    mobility: dict[str, Any] = {}

    if any(token in text for token in WALK_MODE_TOKENS):
        mobility["travel_mode"] = "walk"
    elif any(token in text for token in TRANSIT_MODE_TOKENS):
        mobility["travel_mode"] = "transit"

    if "환승최소" in text or "환승적게" in text or re.search(r"환승(?:은)?(?:최소|적게|줄여)", text):
        mobility["optimize"] = "min_transfers"

    walk_limit = extract_walk_limit(text)
    if walk_limit is not None:
        mobility["max_walk_km_per_day"] = walk_limit
    elif any(token in text for token in LOW_WALK_TOKENS) or re.search(r"걷는거리.*(?:줄여|줄이고|줄여줘)", text):
        mobility["max_walk_km_per_day"] = 5
        mobility.setdefault("travel_mode", "transit")

    if "휠체어" in text:
        mobility["wheelchair"] = True
    if "유모차" in text:
        mobility["stroller"] = True

    return mobility or None

