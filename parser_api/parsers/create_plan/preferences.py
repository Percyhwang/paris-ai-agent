import re

from parser_api.parsers.common.constants import KNOWN_PLACE_TOKENS
from parser_api.parsers.create_plan.constants import THEME_TOKEN_MAP


def _extract_place_preferences(message: str) -> tuple[list[str], list[str]]:
    text = message.replace(" ", "")
    must_include: list[str] = []
    must_avoid: list[str] = []

    for place in KNOWN_PLACE_TOKENS:
        if re.search(rf"{place}(?:은|는|이|가)?(?:꼭|반드시|무조건)", text) or re.search(
            rf"{place}.{{0,10}}(?:넣고싶|넣어줘|포함|가고싶|꼭가고싶|꼭보고싶)",
            text,
        ):
            must_include.append(place)

        if re.search(
            rf"{place}(?:은|는|이|가)?(?:빼줘|빼고|제외|싫어|피하고싶|안가고싶|빼고싶)",
            text,
        ):
            must_avoid.append(place)

    return list(dict.fromkeys(must_include)), list(dict.fromkeys(must_avoid))


def _extract_themes(message: str) -> list[str]:
    compact = message.replace(" ", "")
    themes: list[str] = []

    for theme, tokens in THEME_TOKEN_MAP.items():
        if any(token in compact for token in tokens):
            themes.append(theme)

    return list(dict.fromkeys(themes))

