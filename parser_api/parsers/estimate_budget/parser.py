import re
from typing import Optional

from parser_api.intents import Intent
from parser_api.parsers.hotel_search.parser import _extract_star_rating
from parser_api.parsers.workflow.shared_context.parser import parse_shared_context
from parser_api.schemas import BudgetComponents, Clarify, EstimateBudgetPayload

_COMPONENT_TOKENS = {
    "flight": ("항공권", "비행기", "항공", "flight"),
    "hotel": ("호텔", "숙소", "에어비앤비", "호스텔", "hotel"),
    "food": ("식비", "음식", "맛집", "레스토랑", "food", "meal", "restaurant"),
    "transport": ("교통", "지하철", "버스", "택시", "transport", "transit"),
    "activities": ("입장료", "관광", "액티비티", "박물관", "미술관", "activity", "activities", "museum"),
    "shopping": ("쇼핑", "기념품", "shopping", "souvenir"),
}
_EXCLUDE_SUFFIXES = ("빼고", "제외", "없이", "제외하고")
_ALL_INCLUDE_TOKENS = ("다포함", "모두포함", "전부포함", "전체포함")
_QUALIFIER_SUFFIXES = ("기준", "기준으로")


def _infer_components(message: str) -> BudgetComponents:
    compact = message.replace(" ", "").lower()
    selection_text = re.sub(r"\d성급(?:호텔|숙소)기준(?:으로)?", "", compact)
    selection_text = re.sub(r"(?:호텔|숙소)기준(?:으로)?", "", selection_text)
    mentioned: dict[str, bool] = {}
    excluded: set[str] = set()
    has_all_include = any(token in selection_text for token in _ALL_INCLUDE_TOKENS)

    for component, tokens in _COMPONENT_TOKENS.items():
        for token in tokens:
            if token not in selection_text:
                continue
            if any(f"{token}{suffix}" in selection_text for suffix in _QUALIFIER_SUFFIXES):
                continue
            mentioned[component] = True
            if any(f"{token}{suffix}" in selection_text for suffix in _EXCLUDE_SUFFIXES):
                excluded.add(component)

    if has_all_include:
        components = BudgetComponents()
        for component in excluded:
            setattr(components, component, False)
        return components

    if mentioned:
        components = BudgetComponents(
            flight=False,
            hotel=False,
            food=False,
            transport=False,
            activities=False,
            shopping=False,
        )
        for component in mentioned:
            setattr(components, component, component not in excluded)
        return components

    components = BudgetComponents()
    for component in excluded:
        setattr(components, component, False)
    return components


class EstimateBudgetParser:
    intent = Intent.ESTIMATE_BUDGET

    def parse(self, message: str, context: Optional[dict] = None) -> EstimateBudgetPayload:
        shared = parse_shared_context(message, context)

        payload = EstimateBudgetPayload()
        payload.origin = shared.origin
        payload.destination = shared.destination
        payload.dates = shared.dates
        payload.party = shared.party
        payload.budget = shared.budget
        payload.components = _infer_components(message)
        payload.hotel_star_rating = _extract_star_rating(message)

        missing_fields: list[str] = []
        if payload.destination.city is None:
            missing_fields.append("destination")
        if payload.dates.days is None and not (
            payload.dates.start_date and payload.dates.end_date
        ):
            missing_fields.append("dates.days")

        payload.clarify = Clarify(
            needed=len(missing_fields) > 0,
            missing_fields=missing_fields,
        )
        return payload


ESTIMATE_BUDGET_PARSER = EstimateBudgetParser()


def parse_estimate_budget(message: str, context: Optional[dict] = None) -> EstimateBudgetPayload:
    return ESTIMATE_BUDGET_PARSER.parse(message, context)
