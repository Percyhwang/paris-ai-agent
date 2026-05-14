import re
from typing import Optional

from parser_api.intents import Intent
from parser_api.parsers.llm import augment_payload_with_llm
from parser_api.parsers.workflow.shared_context.parser import parse_shared_context
from parser_api.schemas import Clarify, ManageTripPayload


def _extract_trip_id(message: str, context: Optional[dict]) -> Optional[str]:
    if context and isinstance(context.get("trip_id"), str) and context.get("trip_id"):
        return str(context["trip_id"])

    match = re.search(r"\btrip[-_][A-Za-z0-9_-]+\b", message, re.IGNORECASE)
    if match:
        return match.group(0)
    return None


def _infer_operation(text: str) -> str:
    compact = text.replace(" ", "")
    if any(token in compact for token in ("삭제", "지워", "없애", "제거")) or re.search(r"\b(delete|remove)\b", text):
        return "delete"
    if "rename" in text or (
        any(token in compact for token in ("이름", "제목")) and any(token in compact for token in ("바꿔", "변경", "수정", "rename"))
    ):
        return "rename"
    if any(token in compact for token in ("목록", "리스트", "저장한일정", "내일정", "모든일정", "전체일정")):
        return "list"
    if ("savedtrip" in compact or "savedtrips" in compact) or (
        re.search(r"\b(list|show)\b", text) and re.search(r"\b(trip|trips|plan|plans)\b", text)
    ):
        return "list"
    if any(token in compact for token in ("저장", "보관")) or re.search(r"\bsave\b", text):
        return "save"
    return "retrieve"


def _infer_scope(text: str, has_trip_id: bool) -> str:
    compact = text.replace(" ", "")
    if any(token in compact for token in ("모든", "전체")) or re.search(r"\ball\b", text):
        return "all"
    if "최근" in compact or re.search(r"\b(recent|latest)\b", text):
        return "recent"
    if any(token in compact for token in ("저장한", "내일정")) or "saved" in text:
        return "saved"
    return "current" if has_trip_id else "saved"


def _extract_trip_title(message: str) -> Optional[str]:
    quoted_patterns = (
        r'"([^"]+)"',
        r"'([^']+)'",
    )
    for pattern in quoted_patterns:
        match = re.search(pattern, message)
        if match:
            return match.group(1).strip()

    rename_patterns = (
        r"(?:이름|제목)(?:을|를)?\s*(.+?)(?:으로|로)?\s*(?:바꿔|변경|수정)",
        r"(.+?)(?:으로|로)\s*(?:이름|제목)(?:을|를)?\s*(?:바꿔|변경|수정)",
        r"(.+?)(?:으로|로)\s*저장",
        r"(?:이름|제목)(?:을|를)?\s*(.+?)(?:으로|로)?\s*rename",
        r"(.+?)(?:으로|로)\s*rename",
        r"rename\s+(?:trip[-_][A-Za-z0-9_-]+\s+)?to\s+(.+)",
        r"save\s+(?:this\s+)?trip\s+as\s+(.+)",
    )
    for pattern in rename_patterns:
        match = re.search(pattern, message)
        if match:
            candidate = match.group(1).strip(" .")
            if candidate.endswith("으로"):
                candidate = candidate[:-2].strip()
            elif candidate.endswith("로"):
                candidate = candidate[:-1].strip()
            if candidate:
                return candidate
    return None


class ManageTripParser:
    intent = Intent.MANAGE_TRIP

    def parse(self, message: str, context: Optional[dict] = None) -> ManageTripPayload:
        shared = parse_shared_context(message, context)
        lowered = message.lower()

        payload = ManageTripPayload()
        payload.operation = _infer_operation(lowered)
        payload.trip_id = _extract_trip_id(message, context)
        payload.trip_title = _extract_trip_title(message)
        payload.scope = _infer_scope(lowered, bool(payload.trip_id or shared.trip_id))

        if payload.trip_id is None and shared.trip_id is not None:
            payload.trip_id = shared.trip_id
        payload = augment_payload_with_llm(payload, message, context)

        missing_fields: list[str] = []
        if payload.operation in {"retrieve", "delete"} and payload.scope == "current" and payload.trip_id is None:
            missing_fields.append("trip_id")
        if payload.operation == "rename":
            if payload.trip_id is None:
                missing_fields.append("trip_id")
            if payload.trip_title is None:
                missing_fields.append("trip_title")

        payload.clarify = Clarify(
            needed=bool(missing_fields),
            missing_fields=missing_fields,
        )
        return payload


MANAGE_TRIP_PARSER = ManageTripParser()


def parse_manage_trip(message: str, context: Optional[dict] = None) -> ManageTripPayload:
    return MANAGE_TRIP_PARSER.parse(message, context)
