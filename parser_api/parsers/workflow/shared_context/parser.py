import re
from copy import deepcopy
from datetime import date
from typing import Optional

from parser_api.parsers.create_plan.dates import _extract_days, _normalize_date_text
from parser_api.parsers.create_plan.party import _extract_party
from parser_api.schemas import Budget, Clarify, LocationRef, SharedContextPayload

_LOCATION_TOKEN_MAP: dict[str, dict[str, str]] = {
    "파리": {"city": "Paris", "country": "FR"},
    "paris": {"city": "Paris", "country": "FR"},
    "cdg": {"city": "Paris", "country": "FR", "airport_code": "CDG"},
    "ory": {"city": "Paris", "country": "FR", "airport_code": "ORY"},
    "인천": {"city": "Incheon", "country": "KR", "airport_code": "ICN"},
    "icn": {"city": "Incheon", "country": "KR", "airport_code": "ICN"},
    "김포": {"city": "Seoul", "country": "KR", "airport_code": "GMP"},
    "gmp": {"city": "Seoul", "country": "KR", "airport_code": "GMP"},
    "서울": {"city": "Seoul", "country": "KR"},
    "seoul": {"city": "Seoul", "country": "KR"},
}
_TOKEN_PATTERN = "|".join(sorted((re.escape(token) for token in _LOCATION_TOKEN_MAP), key=len, reverse=True))


def _location_from_token(token: str) -> LocationRef:
    return LocationRef(**deepcopy(_LOCATION_TOKEN_MAP[token]))


def _apply_location(target: LocationRef, source: LocationRef) -> None:
    if source.city and not target.city:
        target.city = source.city
    if source.country and not target.country:
        target.country = source.country
    if source.airport_code and not target.airport_code:
        target.airport_code = source.airport_code
    if source.area and not target.area:
        target.area = source.area
    if source.landmark and not target.landmark:
        target.landmark = source.landmark


def _extract_route_locations(message: str) -> tuple[LocationRef, LocationRef]:
    origin = LocationRef()
    destination = LocationRef()
    compact = message.replace(" ", "").lower()

    match = re.search(
        rf"(?P<origin>{_TOKEN_PATTERN})에서(?P<destination>{_TOKEN_PATTERN})(?:로|행|가는|가고|여행)",
        compact,
    )
    if not match:
        match = re.search(
            rf"(?P<origin>{_TOKEN_PATTERN})(?:-|~|→|->)(?P<destination>{_TOKEN_PATTERN})",
            compact,
        )

    if match:
        _apply_location(origin, _location_from_token(match.group("origin")))
        _apply_location(destination, _location_from_token(match.group("destination")))

    for token in re.findall(_TOKEN_PATTERN, compact):
        resolved = _location_from_token(token)
        if origin.city is None and resolved.airport_code in {"ICN", "GMP"}:
            _apply_location(origin, resolved)
            continue
        if destination.city is None and resolved.city == "Paris":
            _apply_location(destination, resolved)

    if destination.city is None and any(token in compact for token in ("여행", "일정", "호텔", "숙소", "항공권", "예산")):
        destination.city = "Paris"
        destination.country = "FR"

    return origin, destination


def _extract_single_anchor_date(message: str) -> Optional[str]:
    compact = _normalize_date_text(message)

    match = re.search(r"(\d{4})년(\d{1,2})월(\d{1,2})일", compact)
    if match:
        year, month, day = map(int, match.groups())
        return date(year, month, day).isoformat()

    match = re.search(r"(\d{1,2})월(\d{1,2})일", compact)
    if match:
        month, day = map(int, match.groups())
        return date(date.today().year, month, day).isoformat()

    return None


def _extract_budget(message: str) -> Budget:
    compact = message.replace(" ", "")
    lowered = compact.lower()
    budget = Budget()
    budget.currency = "EUR" if any(token in lowered for token in ("유로", "eur", "€")) else "KRW"

    def _parse_amount(raw: str, currency: str, unit_is_manwon: bool = False) -> int:
        value = int(raw)
        if unit_is_manwon:
            return value * 10000
        return value

    match = re.search(r"(?:총)?예산(?:은|은)?(\d+)(?:만원|만 원)", compact)
    if not match:
        match = re.search(r"총(\d+)(?:만원|만 원)", compact)
    if match:
        budget.budget_total = _parse_amount(match.group(1), budget.currency, unit_is_manwon=True)

    if budget.budget_total is None:
        match = re.search(r"(?:총)?예산(?:은|은)?(\d+)(?:원|유로|eur)", lowered)
        if match:
            budget.budget_total = _parse_amount(match.group(1), budget.currency)

    match = re.search(r"하루(\d+)(?:만원|만 원)", compact)
    if match:
        budget.budget_per_day = _parse_amount(match.group(1), budget.currency, unit_is_manwon=True)
    else:
        match = re.search(r"하루(\d+)(?:원|유로|eur)", lowered)
        if match:
            budget.budget_per_day = _parse_amount(match.group(1), budget.currency)

    if any(token in compact for token in ("가성비", "저렴", "아껴", "알뜰")):
        budget.budget_mode = "save"
    elif any(token in compact for token in ("럭셔리", "고급", "프리미엄", "호화")):
        budget.budget_mode = "flex"

    return budget


class SharedContextParser:
    def parse(self, message: str, context: Optional[dict] = None) -> SharedContextPayload:
        payload = SharedContextPayload()
        payload.trip_id = (
            str(context.get("trip_id"))
            if context and isinstance(context.get("trip_id"), str) and context.get("trip_id")
            else None
        )

        origin, destination = _extract_route_locations(message)
        payload.origin = origin
        payload.destination = destination

        days, start_iso, end_iso, source = _extract_days(message)
        payload.dates.days = max(1, days) if isinstance(days, int) else None
        payload.dates.start_date = start_iso
        payload.dates.end_date = end_iso
        payload.dates.source = source

        anchor_date = _extract_single_anchor_date(message)
        if payload.dates.start_date is None and anchor_date is not None:
            payload.dates.start_date = anchor_date
            payload.dates.source = "explicit"

        party = _extract_party(message)
        payload.party.adult = int(party.get("adult", 0))
        payload.party.highschool = int(party.get("highschool", 0))
        payload.party.middleschool = int(party.get("middleschool", 0))
        payload.party.elementary = int(party.get("elementary", 0))
        payload.party.toddler = int(party.get("toddler", 0))
        payload.party.trip_style = str(party.get("trip_style", "unknown"))

        payload.budget = _extract_budget(message)

        payload.clarify = Clarify(needed=False, missing_fields=[])
        return payload


SHARED_CONTEXT_PARSER = SharedContextParser()


def parse_shared_context(message: str, context: Optional[dict] = None) -> SharedContextPayload:
    return SHARED_CONTEXT_PARSER.parse(message, context)
