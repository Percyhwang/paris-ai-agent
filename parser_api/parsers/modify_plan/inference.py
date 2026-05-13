import re
from typing import Any, Optional

from parser_api.parsers.common.constants import (
    FAST_PACE_TOKENS,
    LOW_WALK_TOKENS,
    QUANTITY_TOKEN_PATTERN,
    SLOW_PACE_TOKENS,
)
from parser_api.parsers.common.constants import KOREAN_KNUM_MAP
from parser_api.parsers.common.extractors import extract_slots_in_order
from parser_api.parsers.modify_plan.constants import KNOWN_PLACES

CUISINE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pasta", ("\ud30c\uc2a4\ud0c0", "pasta")),
    ("pizza", ("\ud53c\uc790", "pizza")),
    ("italian", ("\uc774\ud0c8\ub9ac\uc548", "\uc774\ud0dc\ub9ac", "italian")),
    ("french", ("\ud504\ub791\uc2a4\uc2dd", "\ud504\ub80c\uce58", "french", "bistro", "brasserie")),
    ("korean", ("\ud55c\uc2dd", "\ud55c\uad6d\uc2dd", "korean")),
    ("sushi", ("\uc2a4\uc2dc", "\ucd08\ubc25", "sushi")),
    ("ramen", ("\ub77c\uba58", "\ub77c\uba74", "ramen")),
    ("japanese", ("\uc77c\uc2dd", "\uc77c\ubcf8\uc2dd", "japanese")),
    ("chinese", ("\uc911\uc2dd", "\uc911\uad6d\uc2dd", "chinese")),
    ("thai", ("\ud0dc\uad6d\uc2dd", "\ud0c0\uc774", "thai")),
    ("indian", ("\uc778\ub3c4\uc2dd", "\ucee4\ub9ac", "indian", "curry")),
    ("vietnamese", ("\ubca0\ud2b8\ub0a8\uc2dd", "\ubc18\ubbf8", "\ud3ec", "vietnamese")),
    ("mexican", ("\uba55\uc2dc\uce78", "\ud0c0\ucf54", "mexican", "taco")),
    ("mediterranean", ("\uc9c0\uc911\ud574", "mediterranean")),
    ("lebanese", ("\ub808\ubc14\ub17c", "lebanese")),
    ("moroccan", ("\ubaa8\ub85c\ucf54", "moroccan")),
    ("burger", ("\ubc84\uac70", "burger")),
    ("steak", ("\uc2a4\ud14c\uc774\ud06c", "steak", "steakhouse")),
    ("seafood", ("\ud574\uc0b0\ubb3c", "\uc2dc\ud478\ub4dc", "seafood", "fish")),
    ("vegetarian", ("\ucc44\uc2dd", "\ube44\uac74", "vegetarian", "vegan")),
    ("brunch", ("\ube0c\ub7f0\uce58", "brunch")),
    ("bakery", ("\ube75\uc9d1", "\ubca0\uc774\ucee4\ub9ac", "\ud06c\ub8e8\uc544\uc0c1", "bakery", "croissant")),
    ("coffee", ("\ucee4\ud53c", "coffee")),
    ("dessert", ("\ub514\uc800\ud2b8", "\ucf00\uc774\ud06c", "dessert", "cake")),
)


def _extract_target_day(text: str) -> Optional[int]:
    match = re.search(r"day\s*(\d+)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))

    match = re.search(r"(?:^|[^a-z])d\s*(\d+)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))

    match = re.search(r"(\d+)\s*일\s*차", text)
    if match:
        return int(match.group(1))

    match = re.search(r"(\d+)\s*일\s*째", text)
    if match:
        return int(match.group(1))

    match = re.search(r"(\d+)\s*번째\s*날", text)
    if match:
        return int(match.group(1))

    ordinal_map = {
        "첫째날": 1,
        "둘째날": 2,
        "셋째날": 3,
        "넷째날": 4,
        "다섯째날": 5,
    }
    for token, day in ordinal_map.items():
        if token in text:
            return day

    return None


def _infer_op(text: str) -> str:
    slot_count = sum(
        1
        for token in ("오전", "점심", "오후", "저녁", "밤", "야간", "새벽")
        if token in text
    )
    if slot_count >= 2 and any(token in text for token in ("바꿔", "교체", "스왑")):
        return "swap"

    if re.search(
        rf"({QUANTITY_TOKEN_PATTERN})\s*개(?:를|에서)?\s*({QUANTITY_TOKEN_PATTERN})\s*개(?:로)?",
        text,
    ):
        return "set_quantity"

    if "개" in text and any(token in text for token in ("줄여줘", "늘려줘", "줄여", "늘려")):
        return "set_quantity"

    if ("미술관하루" in text or "박물관하루" in text) and "개만" in text:
        return "set_constraint"

    if any(token in text for token in ("실내위주", "실내로만", "실내만", "비오면", "비올때", "우천", "우천시")):
        return "set_constraint"

    if (
        any(token in text for token in ("도보위주", "도보로만", "걸어서", "걸어다니는", "대중교통위주", "지하철위주", "버스위주", "대중교통으로만", "휠체어", "유모차"))
        or re.search(r"환승(?:은)?(?:최소|적게|줄여)", text)
        or any(token in text for token in LOW_WALK_TOKENS)
        or re.search(r"걷는거리.*(?:줄여|줄이고|줄여줘)", text)
        or re.search(r"(?:하루)?\d+\s*km(?:까지)?(?:이하|이내)", text)
    ):
        return "set_mobility"

    if any(token in text for token in FAST_PACE_TOKENS) or (
        "타이트" in text and not any(token in text for token in ("너무타이트", "타이트해서"))
    ):
        return "set_pace"
    if any(token in text for token in SLOW_PACE_TOKENS):
        return "set_pace"
    if any(token in text for token in ("힘들", "부담", "줄여", "완화", "너무많", "과해", "너무빡세", "빡세서")):
        return "set_pace"

    if any(token in text for token in ("추가", "추가해", "더넣", "하나더", "더넣어")):
        return "add"
    if any(token in text for token in ("빼줘", "제외", "삭제", "제거")):
        return "remove"
    if any(token in text for token in ("대신", "바꿔", "교체")):
        return "replace"
    if any(token in text for token in ("옮겨", "이동")):
        return "move"
    return "replace"


def _infer_category(text: str) -> Optional[str]:
    if "카페" in text:
        return "cafe"
    if "박물관" in text or "미술관" in text:
        return "museum"
    if "야경" in text:
        return "night_view"
    if "공원" in text:
        return "park"
    if "쇼핑" in text:
        return "shopping"
    if "맛집" in text or "식당" in text:
        return "restaurant"
    return None

def _infer_cuisine(text: str) -> Optional[str]:
    lowered = text.lower()
    for cuisine, keywords in CUISINE_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return cuisine
    return None


def _find_place_mentions(message: str) -> list[str]:
    found: list[str] = []
    for place in KNOWN_PLACES:
        if place in message:
            found.append(place)
    return list(dict.fromkeys(found))


def _infer_place_change(message: str) -> tuple[Optional[str], Optional[str]]:
    msg = message.replace(" ", "")

    for pattern in (
        r"(.+?)(?:대신|말고)(.+)",
        r"(.+?)(?:->|→)(.+)",
        r"(.+?)(?:을|를)(.+?)(?:로)(?:바꿔|교체|변경)",
        r"(.+?)에서(.+?)로(?:바꿔|교체|변경)?",
        r"(.+?)빼고(.+?)(?:넣어|추가)",
    ):
        match = re.search(pattern, msg)
        if not match:
            continue
        left, right = match.group(1), match.group(2)
        from_candidates = [place for place in KNOWN_PLACES if place in left]
        to_candidates = [place for place in KNOWN_PLACES if place in right]
        return (
            from_candidates[0] if from_candidates else None,
            to_candidates[0] if to_candidates else None,
        )

    return None, None


def _infer_place_name(message: str, op: str) -> Optional[str]:
    mentions = _find_place_mentions(message)
    if op == "replace":
        from_place, _ = _infer_place_change(message)
        if from_place:
            return from_place
    return mentions[0] if mentions else None


def _infer_replace_targets(message: str, category: Optional[str]) -> Optional[dict[str, Any]]:
    if not any(
        token in message
        for token in ("대신", "말고", "->", "→", "바꿔", "교체", "변경", "빼고")
    ):
        return None

    from_place, to_place = _infer_place_change(message)
    if from_place and to_place:
        return {
            "replace_mode": "place_to_place",
            "from_place": from_place,
            "to_place": to_place,
        }
    if from_place and category:
        return {
            "replace_mode": "place_to_category",
            "from_place": from_place,
            "to_category": category,
        }
    return None


def _infer_quantity(text: str) -> Optional[int]:
    match = re.search(r"(\d+)\s*개(?:만|더)?", text)
    if match:
        return int(match.group(1))

    match = re.search(r"(하나|한|둘|두|셋|세|넷|네|다섯|여섯|일곱|여덟|아홉|열)\s*개(?:만|더)?", text)
    if match:
        return KOREAN_KNUM_MAP[match.group(1)]

    match = re.search(r"(하나|둘|셋|넷|다섯|여섯|일곱|여덟|아홉|열)(?:개)?\s*(?:추가|더넣|더넣어|넣어줘)", text)
    if match:
        return KOREAN_KNUM_MAP[match.group(1)]

    if "하나더" in text or "하나 더" in text:
        return 1
    return None


def _infer_quantity_change(text: str) -> tuple[Optional[int], Optional[int]]:
    match = re.search(
        rf"({QUANTITY_TOKEN_PATTERN})\s*개(?:를|에서)?\s*({QUANTITY_TOKEN_PATTERN})\s*개(?:로)?",
        text,
    )
    if not match:
        return None, None

    def _parse_num(token: str) -> int:
        if token.isdigit():
            return int(token)
        return KOREAN_KNUM_MAP[token]

    return _parse_num(match.group(1)), _parse_num(match.group(2))


def _infer_target_slot(text: str) -> Optional[str]:
    slots = extract_slots_in_order(text)
    if slots:
        return slots[0]
    lowered = text.lower()
    if any(token in lowered for token in ("\uc544\uce68", "\uc624\uc804", "morning", "breakfast")):
        return "morning"
    if any(token in lowered for token in ("\uc810\uc2ec", "\ube0c\ub7f0\uce58", "lunch", "brunch")):
        return "lunch"
    if any(token in lowered for token in ("\uc624\ud6c4", "afternoon")):
        return "afternoon"
    if any(token in lowered for token in ("\uc800\ub141", "\ubc24", "dinner", "evening", "night")):
        return "dinner"
    return None
