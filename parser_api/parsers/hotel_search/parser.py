import re
from datetime import date
from typing import Optional

from parser_api.intents import Intent
from parser_api.parsers.workflow.shared_context.parser import parse_shared_context
from parser_api.schemas import Clarify, HotelSearchPayload

_LANDMARK_MAP = {
    "에펠탑": ("near_eiffel_tower", "eiffel_tower"),
    "루브르": ("near_louvre", "louvre"),
    "오르세": ("near_orsay", "orsay"),
    "샹젤리제": ("near_champs_elysees", "champs_elysees"),
    "몽마르트": ("near_montmartre", "montmartre"),
    "오페라": ("near_opera", "opera"),
}


def _extract_star_rating(text: str) -> Optional[int]:
    compact = text.replace(" ", "").lower()
    match = re.search(r"([1-5])성급", compact)
    if match:
        return int(match.group(1))
    match = re.search(r"([1-5])-?star", compact)
    if match:
        return int(match.group(1))
    return None


def _extract_rooms(text: str) -> int:
    compact = text.replace(" ", "")
    match = re.search(r"(?:방|객실)(\d+)개", compact)
    if match:
        return max(1, int(match.group(1)))
    match = re.search(r"(\d+)개(?:의)?(?:방|객실)", compact)
    if match:
        return max(1, int(match.group(1)))
    return 1


def _extract_area_and_landmark(text: str) -> tuple[Optional[str], Optional[str]]:
    compact = text.replace(" ", "")
    for token, (area, landmark) in _LANDMARK_MAP.items():
        if token in compact:
            return area, landmark
    return None, None


def _extract_max_price_per_night(text: str) -> tuple[Optional[int], str]:
    compact = text.replace(" ", "")
    currency = "EUR" if any(token in compact.lower() for token in ("유로", "eur", "€")) else "KRW"

    match = re.search(
        r"(?:1박|박당|하루)\s*(\d+)(?:만원|만 원|원|유로|eur|€)(?:이하|이내|정도)?",
        text,
        re.IGNORECASE,
    )
    if match:
        raw_amount = int(match.group(1))
        if "만원" in match.group(0) or "만 원" in match.group(0):
            return raw_amount * 10000, currency
        return raw_amount, currency

    match = re.search(
        r"(?:호텔|숙소)\s*(\d+)(?:만원|만 원|원|유로|eur|€)(?:이하|이내|정도)?",
        text,
        re.IGNORECASE,
    )
    if match:
        raw_amount = int(match.group(1))
        if "만원" in match.group(0) or "만 원" in match.group(0):
            return raw_amount * 10000, currency
        return raw_amount, currency

    return None, currency


def _infer_nights(check_in_date: Optional[str], check_out_date: Optional[str], days: Optional[int]) -> Optional[int]:
    if check_in_date and check_out_date:
        start = date.fromisoformat(check_in_date)
        end = date.fromisoformat(check_out_date)
        delta = (end - start).days
        if delta >= 1:
            return delta
    if days and days >= 2:
        return days - 1
    return None


class HotelSearchParser:
    intent = Intent.HOTEL_SEARCH

    def parse(self, message: str, context: Optional[dict] = None) -> HotelSearchPayload:
        shared = parse_shared_context(message, context)

        payload = HotelSearchPayload()
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

        missing_fields: list[str] = []
        if payload.destination.city is None:
            missing_fields.append("destination")
        if payload.check_in_date is None and payload.nights is None:
            missing_fields.append("check_in_date")

        payload.clarify = Clarify(
            needed=len(missing_fields) > 0,
            missing_fields=missing_fields,
        )
        return payload


HOTEL_SEARCH_PARSER = HotelSearchParser()


def parse_hotel_search(message: str, context: Optional[dict] = None) -> HotelSearchPayload:
    return HOTEL_SEARCH_PARSER.parse(message, context)
