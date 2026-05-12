import re
from typing import Optional

from parser_api.intents import Intent
from parser_api.parsers.modify_plan.constants import KNOWN_PLACES
from parser_api.parsers.modify_plan.inference import _extract_target_day
from parser_api.parsers.workflow.shared_context.parser import parse_shared_context
from parser_api.schemas import Clarify, TripDiaryPayload


def _extract_highlights(message: str) -> list[str]:
    highlights: list[str] = []
    for place in KNOWN_PLACES:
        if place in message:
            highlights.append(place)
    return list(dict.fromkeys(highlights))


def _infer_tone(text: str) -> str:
    if any(token in text for token in ("감성", "감성적", "서정", "감동", "emotional")):
        return "emotional"
    if "블로그" in text or "blog" in text:
        return "blog"
    if any(token in text for token in ("정보", "설명", "요약", "informative")):
        return "informative"
    return "casual"


def _infer_format(text: str) -> str:
    if any(token in text for token in ("리스트", "불릿", "bullet")):
        return "bullet"
    if any(token in text for token in ("타임라인", "시간순", "timeline")):
        return "timeline"
    return "paragraph"


def _extract_notes(message: str) -> Optional[str]:
    patterns = (
        r"메모[:：]\s*(.+)",
        r"포인트[:：]\s*(.+)",
        r"note[:：]\s*(.+)",
    )
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return match.group(1).strip()
    return None


class TripDiaryParser:
    intent = Intent.TRIP_DIARY

    def parse(self, message: str, context: Optional[dict] = None) -> TripDiaryPayload:
        shared = parse_shared_context(message, context)
        compact = message.replace(" ", "").lower()

        payload = TripDiaryPayload()
        payload.trip_id = shared.trip_id
        payload.target_day = _extract_target_day(message.replace(" ", ""))
        payload.entry_date = (
            shared.dates.start_date
            if shared.dates.start_date is not None and shared.dates.end_date is None
            else None
        )
        payload.tone = _infer_tone(compact)
        payload.format = _infer_format(compact)
        payload.include_weather = any(token in compact for token in ("날씨", "기온", "비", "맑음"))
        payload.include_cost = any(token in compact for token in ("비용", "예산", "경비", "지출"))
        payload.highlights = _extract_highlights(message)
        payload.notes = _extract_notes(message)

        missing_fields: list[str] = []
        if (
            payload.trip_id is None
            and payload.target_day is None
            and payload.entry_date is None
            and not payload.highlights
        ):
            missing_fields.append("trip_scope")

        payload.clarify = Clarify(
            needed=bool(missing_fields),
            missing_fields=missing_fields,
        )
        return payload


TRIP_DIARY_PARSER = TripDiaryParser()


def parse_trip_diary(message: str, context: Optional[dict] = None) -> TripDiaryPayload:
    return TRIP_DIARY_PARSER.parse(message, context)
