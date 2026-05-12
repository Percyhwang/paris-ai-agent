import re
from typing import Optional

from parser_api.intents import Intent
from parser_api.parsers.workflow.shared_context.parser import parse_shared_context
from parser_api.schemas import Clarify, FlightSearchPayload


def _infer_trip_type(text: str) -> str:
    if "편도" in text:
        return "one_way"
    if "왕복" in text:
        return "round_trip"
    return "round_trip"


def _infer_cabin_class(text: str) -> str:
    if any(token in text for token in ("premiumeconomy", "프리미엄이코노미")):
        return "premium_economy"
    if any(token in text for token in ("비즈니스", "business")):
        return "business"
    if any(token in text for token in ("퍼스트", "first")):
        return "first"
    return "economy"


def _extract_max_price(text: str) -> tuple[Optional[int], str]:
    compact = text.replace(" ", "")
    currency = "EUR" if any(token in compact.lower() for token in ("유로", "eur", "€")) else "KRW"

    match = re.search(
        r"항공권.{0,30}?(\d+)\s*(?=(?:만원|만 원|원|유로|eur))(?:만원|만 원|원|유로|eur)(?:\s*(?:이하|이내|정도))?",
        text,
        re.IGNORECASE,
    )
    if match:
        raw_amount = match.group(1)
        if "만원" in match.group(0) or "만 원" in match.group(0):
            return int(raw_amount) * 10000, currency
        return int(raw_amount), currency

    match = re.search(r"항공권(?:은|은)?(\d+)(?:만원|만 원)(?:이하|이내|정도)?", compact)
    if match:
        return int(match.group(1)) * 10000, currency

    match = re.search(r"(\d+)(?:만원|만 원)(?:이하|이내).{0,6}항공권", compact)
    if match:
        return int(match.group(1)) * 10000, currency

    match = re.search(r"항공권.{0,20}(\d+)(?:만원|만 원)(?:이하|이내|정도)?", compact)
    if match:
        return int(match.group(1)) * 10000, currency

    match = re.search(r"항공권(?:은|은)?(\d+)(?:원|유로|eur)", compact.lower())
    if match:
        return int(match.group(1)), currency

    return None, currency


class FlightSearchParser:
    intent = Intent.FLIGHT_SEARCH

    def parse(self, message: str, context: Optional[dict] = None) -> FlightSearchPayload:
        shared = parse_shared_context(message, context)
        compact = message.replace(" ", "").lower()

        payload = FlightSearchPayload()
        payload.origin = shared.origin
        payload.destination = shared.destination
        payload.departure_date = shared.dates.start_date
        payload.return_date = shared.dates.end_date
        payload.trip_type = _infer_trip_type(compact)
        payload.cabin_class = _infer_cabin_class(compact)
        payload.direct_only = "직항" in compact
        payload.party = shared.party
        payload.max_price, payload.currency = _extract_max_price(message)

        missing_fields: list[str] = []
        if payload.origin.airport_code is None and payload.origin.city is None:
            missing_fields.append("origin")
        if payload.departure_date is None:
            missing_fields.append("departure_date")
        if payload.destination.city is None:
            missing_fields.append("destination")

        payload.clarify = Clarify(
            needed=len(missing_fields) > 0,
            missing_fields=missing_fields,
        )
        return payload


FLIGHT_SEARCH_PARSER = FlightSearchParser()


def parse_flight_search(message: str, context: Optional[dict] = None) -> FlightSearchPayload:
    return FLIGHT_SEARCH_PARSER.parse(message, context)
