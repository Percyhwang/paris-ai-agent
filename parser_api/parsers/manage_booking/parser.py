import re
from typing import Optional

from parser_api.intents import Intent
from parser_api.parsers.hotel_search.parser import (
    _extract_area_and_landmark,
    _extract_rooms,
    _extract_star_rating,
)
from parser_api.parsers.workflow.shared_context.parser import parse_shared_context
from parser_api.schemas import BookingChangeRequest, Clarify, ManageBookingPayload


def _extract_booking_id(message: str, context: Optional[dict]) -> Optional[str]:
    if context:
        for key in ("booking_id", "reservation_id"):
            value = context.get(key)
            if isinstance(value, str) and value:
                return value

    patterns = (
        r"(?:booking|reservation)\s*id\s*[:#]?\s*([A-Za-z0-9_-]+)",
        r"(?:예약번호|예약id)\s*[:#]?\s*([A-Za-z0-9_-]+)",
        r"(?:booking|reservation)\s*[:#]?\s*([A-Za-z0-9_-]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _infer_operation(text: str) -> str:
    if "취소" in text or "cancel" in text:
        return "cancel"
    if any(token in text for token in ("변경", "수정", "바꿔", "업데이트")):
        return "modify"
    return "retrieve"


def _infer_booking_domain(text: str) -> str:
    has_flight = any(token in text for token in ("항공권", "비행기", "flight", "항공"))
    has_hotel = any(token in text for token in ("호텔", "숙소", "hotel", "에어비앤비"))

    if has_flight and has_hotel:
        return "mixed"
    if has_flight:
        return "flight"
    if has_hotel:
        return "hotel"
    return "unknown"


def _has_explicit_guest_signal(message: str) -> bool:
    compact = message.replace(" ", "")
    return bool(
        re.search(r"\d+\s*명", compact)
        or any(token in compact for token in ("혼자", "부부", "커플", "둘이", "둘이서", "셋이", "셋이서", "넷이", "넷이서"))
    )


def _build_change_request(message: str, context: Optional[dict]) -> BookingChangeRequest:
    shared = parse_shared_context(message, context)
    area, landmark = _extract_area_and_landmark(message)

    change_request = BookingChangeRequest()
    change_request.check_in_date = shared.dates.start_date
    change_request.check_out_date = shared.dates.end_date
    change_request.departure_date = shared.dates.start_date
    change_request.return_date = shared.dates.end_date
    guests = shared.party.total
    if guests > 0 and _has_explicit_guest_signal(message):
        change_request.guests = guests
    rooms = _extract_rooms(message)
    if rooms > 1 or "방" in message or "객실" in message:
        change_request.rooms = rooms
    change_request.star_rating = _extract_star_rating(message)
    change_request.area = area
    change_request.landmark = landmark
    return change_request


class ManageBookingParser:
    intent = Intent.MANAGE_BOOKING

    def parse(self, message: str, context: Optional[dict] = None) -> ManageBookingPayload:
        shared = parse_shared_context(message, context)
        compact = message.replace(" ", "").lower()

        payload = ManageBookingPayload()
        payload.operation = _infer_operation(compact)
        payload.booking_domain = _infer_booking_domain(compact)
        payload.booking_id = _extract_booking_id(message, context)
        payload.trip_id = shared.trip_id
        payload.change_request = _build_change_request(message, context)
        payload.requires_confirmation = payload.operation == "cancel"

        missing_fields: list[str] = []
        if payload.booking_id is None and payload.trip_id is None:
            missing_fields.append("booking_id")
        if payload.operation == "modify":
            has_change = any(
                getattr(payload.change_request, field) is not None
                for field in (
                    "check_in_date",
                    "check_out_date",
                    "departure_date",
                    "return_date",
                    "guests",
                    "rooms",
                    "star_rating",
                    "area",
                    "landmark",
                    "notes",
                )
            )
            if not has_change:
                missing_fields.append("change_request")

        payload.clarify = Clarify(
            needed=bool(missing_fields),
            missing_fields=missing_fields,
        )
        return payload


MANAGE_BOOKING_PARSER = ManageBookingParser()


def parse_manage_booking(message: str, context: Optional[dict] = None) -> ManageBookingPayload:
    return MANAGE_BOOKING_PARSER.parse(message, context)
