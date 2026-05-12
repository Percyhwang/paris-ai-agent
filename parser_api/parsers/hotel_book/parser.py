import re
from typing import Optional

from parser_api.intents import Intent
from parser_api.parsers.hotel_search.parser import (
    _extract_area_and_landmark,
    _extract_max_price_per_night,
    _extract_rooms,
    _extract_star_rating,
    _infer_nights,
)
from parser_api.parsers.workflow.shared_context.parser import parse_shared_context
from parser_api.schemas import Clarify, HotelBookPayload


def _extract_property_ref(message: str, context: Optional[dict]) -> Optional[str]:
    if context:
        for key in ("property_ref", "hotel_property_ref", "selected_hotel_id"):
            value = context.get(key)
            if isinstance(value, str) and value:
                return value

    patterns = (
        r"(?:property)\s*[:#]?\s*([A-Za-z0-9_-]+)",
        r"(?:호텔|숙소)?옵션\s*[:#]?\s*([A-Za-z0-9_-]+)",
        r"([A-Za-z0-9_-]+)(?:번|옵션)(?:으로|로)?\s*예약",
    )
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


class HotelBookParser:
    intent = Intent.HOTEL_BOOK

    def parse(self, message: str, context: Optional[dict] = None) -> HotelBookPayload:
        shared = parse_shared_context(message, context)

        payload = HotelBookPayload()
        payload.destination = shared.destination
        payload.area, payload.landmark = _extract_area_and_landmark(message)
        payload.check_in_date = shared.dates.start_date
        payload.check_out_date = shared.dates.end_date
        payload.nights = _infer_nights(
            payload.check_in_date,
            payload.check_out_date,
            shared.dates.days,
        )
        payload.guests = max(1, shared.party.total)
        payload.rooms = _extract_rooms(message)
        payload.star_rating = _extract_star_rating(message)
        payload.max_price_per_night, payload.currency = _extract_max_price_per_night(message)
        payload.property_ref = _extract_property_ref(message, context)
        payload.requires_confirmation = True

        missing_fields: list[str] = []
        if payload.destination.city is None:
            missing_fields.append("destination")
        if payload.check_in_date is None and payload.nights is None:
            missing_fields.append("check_in_date")
        if payload.property_ref is None:
            missing_fields.append("property_ref")

        payload.clarify = Clarify(
            needed=bool(missing_fields),
            missing_fields=missing_fields,
        )
        return payload


HOTEL_BOOK_PARSER = HotelBookParser()


def parse_hotel_book(message: str, context: Optional[dict] = None) -> HotelBookPayload:
    return HOTEL_BOOK_PARSER.parse(message, context)
