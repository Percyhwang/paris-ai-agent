import re
from datetime import date
from typing import Optional


def _normalize_date_text(message: str) -> str:
    normalized = message.replace(" ", "")
    normalized = re.sub(
        r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})",
        r"\1년\2월\3일",
        normalized,
    )
    normalized = re.sub(
        r"(?<!\d)(\d{1,2})[./](\d{1,2})(?!\d)",
        r"\1월\2일",
        normalized,
    )
    return normalized


def _extract_single_date(text: str) -> Optional[str]:
    match = re.search(r"(\d{4})년(\d{1,2})월(\d{1,2})일", text)
    if match:
        year, month, day = map(int, match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None

    match = re.search(r"(\d{1,2})월(\d{1,2})일", text)
    if match:
        month, day = map(int, match.groups())
        try:
            return date(date.today().year, month, day).isoformat()
        except ValueError:
            return None

    return None


def _extract_days(message: str) -> tuple[Optional[int], Optional[str], Optional[str], str]:
    text = _normalize_date_text(message)

    def _calc_range_days(
        y1: int,
        m1: int,
        d1: int,
        y2: int,
        m2: int,
        d2: int,
    ) -> tuple[int, str, str]:
        start = date(y1, m1, d1)
        end = date(y2, m2, d2)
        delta = (end - start).days + 1
        if delta < 1:
            raise ValueError("End date before start date.")
        return delta, start.isoformat(), end.isoformat()

    match = re.search(
        r"(\d{4})년(\d{1,2})월(\d{1,2})일(?:부터|~|-|–|—)?(\d{4})년(\d{1,2})월(\d{1,2})일(?:까지)?",
        text,
    )
    if match:
        try:
            y1, mo1, d1, y2, mo2, d2 = map(int, match.groups())
            days, start_iso, end_iso = _calc_range_days(y1, mo1, d1, y2, mo2, d2)
            return days, start_iso, end_iso, "explicit"
        except ValueError:
            return None, None, None, "missing"

    match = re.search(
        r"(\d{1,2})월(\d{1,2})일(?:부터|~|-|–|—)?(\d{1,2})월(\d{1,2})일(?:까지)?",
        text,
    )
    if match:
        try:
            mo1, d1, mo2, d2 = map(int, match.groups())
            year = date.today().year
            days, start_iso, end_iso = _calc_range_days(year, mo1, d1, year, mo2, d2)
            return days, start_iso, end_iso, "explicit"
        except ValueError:
            return None, None, None, "missing"

    match = re.search(r"(\d{1,2})월(\d{1,2})일(?:부터|~|-|–|—)?(\d{1,2})일(?:까지)?", text)
    if match:
        try:
            month, d1, d2 = map(int, match.groups())
            year = date.today().year
            days, start_iso, end_iso = _calc_range_days(year, month, d1, year, month, d2)
            return days, start_iso, end_iso, "explicit"
        except ValueError:
            return None, None, None, "missing"

    match = re.search(r"(\d+)박(\d+)일", text)
    if match:
        return int(match.group(2)), _extract_single_date(text), None, "explicit"

    single_date = _extract_single_date(text)
    if single_date is not None:
        return None, single_date, None, "explicit"

    for match in re.finditer(r"(\d+)\s*일", message):
        prefix = message[: match.start()].rstrip()
        if prefix.endswith("월"):
            continue
        return int(match.group(1)), None, None, "explicit"

    return None, None, None, "missing"
