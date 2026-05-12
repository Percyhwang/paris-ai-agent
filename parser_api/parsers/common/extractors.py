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
    match = re.search(r"(?:박물관|미술관)(?:은)?하루(\d+)개만", text)
    if match:
        return int(match.group(1))

    match = re.search(
        r"(?:박물관|미술관)(?:은)?하루(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)개만",
        text,
    )
    if match:
        return KOREAN_KNUM_MAP[match.group(1)]
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
