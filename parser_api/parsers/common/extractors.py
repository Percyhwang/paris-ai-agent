import re
from typing import Optional

from parser_api.parsers.common.constants import (
    KOREAN_KNUM_MAP,
    SLOT_PATTERNS,
)


def extract_walk_limit(text: str) -> Optional[int]:
    match = re.search(r"(?:하루)?(\d+)\s*km(?:까지)?(?:이하|이내)", text)
    if match:
        return int(match.group(1))
    return None


def extract_museum_limit(text: str) -> Optional[int]:
    compact = re.sub(r"\s+", "", text or "").lower()
    if any(token in compact for token in ("박물관", "미술관", "museum")):
        if any(
            token in compact
            for token in (
                "하나이하",
                "한개이하",
                "1개이하",
                "하나만",
                "한곳만",
                "대표하나",
                "atmostone",
                "oneonly",
            )
        ):
            return 1
        if any(token in compact for token in ("두개이하", "2개이하", "두곳이하", "둘이하", "atmosttwo")):
            return 2

    match = re.search(r"(?:박물관|미술관)(?:은|는)?하루(\d+)개만", compact)
    if match:
        return int(match.group(1))

    match = re.search(r"(?:박물관|미술관)(?:은|는)?하루(하나|한곳|두곳|두개|셋|세개|네개|네곳)만", compact)
    if match:
        return {"하나": 1, "한곳": 1, "두곳": 2, "두개": 2, "셋": 3, "세개": 3, "네개": 4, "네곳": 4}.get(
            match.group(1)
        ) or KOREAN_KNUM_MAP.get(match.group(1))
    return None


def extract_slots_in_order(text: str) -> list[str]:
    candidates = []
    for token, slot in SLOT_PATTERNS:
        index = text.find(token)
        if index >= 0:
            candidates.append((index, slot))

    ordered_slots: list[str] = []
    for _, slot in sorted(candidates, key=lambda item: item[0]):
        if slot not in ordered_slots:
            ordered_slots.append(slot)
    return ordered_slots
