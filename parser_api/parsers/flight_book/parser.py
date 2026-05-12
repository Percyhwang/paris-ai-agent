import re
from typing import Optional

from parser_api.intents import Intent
from parser_api.parsers.flight_search.parser import (
    _extract_max_price,
    _infer_cabin_class,
    _infer_trip_type,
)
from parser_api.parsers.workflow.shared_context.parser import parse_shared_context
from parser_api.schemas import Clarify, FlightBookPayload


def _extract_offer_ref(message: str, context: Optional[dict]) -> Optional[str]:
    if context:
        for key in ("offer_ref", "flight_offer_ref", "selected_flight_id"):
            value = context.get(key)
            if isinstance(value, str) and value:
                return value

    patterns = (
        r"(?:오퍼|offer)\s*[:#]?\s*([A-Za-z0-9_-]+)",
        r"(?:항공권|비행기표)?옵션\s*[:#]?\s*([A-Za-z0-9_-]+)",
        r"([A-Za-z0-9_-]+)(?:번|옵션)(?:으로|로)?\s*예약",
    )
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


class FlightBookParser:
    intent = Intent.FLIGHT_BOOK

    def parse(self, message: str, context: Optional[dict] = None) -> FlightBookPayload:
        shared = parse_shared_context(message, context)
        compact = message.replace(" ", "").lower()

        payload = FlightBookPayload()
        payload.origin = shared.origin
        payload.destination = shared.destination
        payload.departure_date = shared.dates.start_date
        payload.return_date = shared.dates.end_date
        payload.trip_type = _infer_trip_type(compact)
        payload.cabin_class = _infer_cabin_class(compact)
        payload.direct_only = "직항" in compact
        payload.party = shared.party
        payload.max_price, payload.currency = _extract_max_price(message)
        payload.offer_ref = _extract_offer_ref(message, context)
        payload.requires_confirmation = True

        missing_fields: list[str] = []
        if payload.origin.airport_code is None and payload.origin.city is None:
            missing_fields.append("origin")
        if payload.destination.city is None:
            missing_fields.append("destination")
        if payload.departure_date is None:
            missing_fields.append("departure_date")
        if payload.offer_ref is None:
            missing_fields.append("offer_ref")

        payload.clarify = Clarify(
            needed=bool(missing_fields),
            missing_fields=missing_fields,
        )
        return payload


FLIGHT_BOOK_PARSER = FlightBookParser()


def parse_flight_book(message: str, context: Optional[dict] = None) -> FlightBookPayload:
    return FLIGHT_BOOK_PARSER.parse(message, context)
