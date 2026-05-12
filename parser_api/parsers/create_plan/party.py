import re
from typing import Any

from parser_api.parsers.common.constants import KOREAN_KNUM_MAP
from parser_api.parsers.create_plan.constants import (
    FAMILY_TOKENS,
    FILIAL_THEME_TOKENS,
    GENERIC_CHILD_TOKENS,
    KIN_PREFIX_PATTERN,
    KOREAN_TOTAL_MAP,
    ROMANCE_COUPLE_TOKENS,
)


def _infer_include_speaker(text: str) -> bool:
    if (
        ("여행가신다고" in text or "여행가시" in text or "가신다고" in text)
        and "내가" in text
        and "계획" in text
    ):
        return False

    if re.search(
        r"[가-힣]{1,12}(?:이랑|랑|와|과|하고)[가-힣]{1,12}(?:이|가)(?!랑).{0,12}여행(?:가|간|갈)",
        text,
    ):
        return False

    if any(t in text for t in ("내가", "우리", "나랑", "저랑", "제가", "같이", "모시고")):
        return True

    has_trip_request = any(
        token in text
        for token in (
            "여행",
            "일정",
            "계획",
            "코스",
            "일정표",
            "짜줘",
            "세워",
            "구성",
            "다녀오",
            "놀러",
            "가고싶",
            "가고싶어",
            "가볼",
            "갈래",
            "가자",
            "떠나",
            "출발",
        )
    )
    companion_count = len(re.findall(r"(?:이랑|랑|하고|과|와)", text))
    has_family = any(token in text for token in FAMILY_TOKENS) or any(
        token in text for token in GENERIC_CHILD_TOKENS
    )

    return has_trip_request and has_family and companion_count >= 1


def _extract_generic_child_count(text: str) -> int:
    total = 0
    child_pattern = r"(?:아이들|아이|애들|애|아들|딸|자녀)"
    knum = r"(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)"

    for match in re.finditer(rf"{child_pattern}\s*(\d+)\s*명", text):
        total += int(match.group(1))
    for match in re.finditer(rf"(\d+)\s*명의?\s*{child_pattern}", text):
        total += int(match.group(1))
    for match in re.finditer(rf"{child_pattern}{knum}\s*명", text):
        total += KOREAN_KNUM_MAP[match.group(1)]
    for match in re.finditer(rf"{knum}\s*명의?\s*{child_pattern}", text):
        total += KOREAN_KNUM_MAP[match.group(1)]

    if total > 0:
        return total
    return 1 if any(token in text for token in GENERIC_CHILD_TOKENS) else 0


def _count_family_members(text: str) -> int:
    def _count_for_token(token: str, default_if_present: int = 1) -> int:
        total = 0
        token_pattern = re.escape(token)
        if token == "이모":
            token_pattern = r"이모(?!부|할머니|할아버지)"
        elif token == "고모":
            token_pattern = r"고모(?!부)"
        elif token == "할머니":
            token_pattern = r"(?<!친)(?<!외)(?<!이모)할머니"
        elif token == "할아버지":
            token_pattern = r"(?<!친)(?<!외)(?<!이모)할아버지"

        for match in re.finditer(rf"{token_pattern}\s*(\d+)\s*명", text):
            total += int(match.group(1))
        for match in re.finditer(rf"(\d+)\s*명의?\s*{token_pattern}", text):
            total += int(match.group(1))

        knum = r"(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)"
        for match in re.finditer(rf"{token_pattern}{knum}\s*명", text):
            total += KOREAN_KNUM_MAP[match.group(1)]
        for match in re.finditer(rf"{knum}\s*명의?\s*{token_pattern}", text):
            total += KOREAN_KNUM_MAP[match.group(1)]

        if total > 0:
            return total
        return default_if_present if re.search(token_pattern, text) else 0

    family_total = 0
    if "부모님" in text:
        family_total += 2
    else:
        family_total += _count_for_token("엄마")
        family_total += _count_for_token("아빠")

    for token in (
        "형",
        "누나",
        "동생",
        "사촌",
        "조카",
        "외할아버지",
        "외할머니",
        "친할아버지",
        "친할머니",
        "할머니",
        "할아버지",
        "이모",
        "이모부",
        "고모",
        "고모부",
        "삼촌",
        "숙모",
        "이모할머니",
        "이모할아버지",
    ):
        family_total += _count_for_token(token)
    return family_total


def _extract_party(message: str) -> dict[str, Any]:
    text = message.replace(" ", "")
    party: dict[str, Any] = {
        "adult": 0,
        "highschool": 0,
        "middleschool": 0,
        "elementary": 0,
        "toddler": 0,
        "trip_style": "unknown",
    }

    def _parse_count(token: str) -> int:
        if token.isdigit():
            return int(token)
        return KOREAN_KNUM_MAP[token]

    def _sum_matches(patterns: tuple[str, ...]) -> int:
        total = 0
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                total += _parse_count(match.group(1))
        return total

    count_token = r"\d+|한|두|세|네|다섯|여섯|일곱|여덟|아홉|열"
    party["highschool"] = _sum_matches(
        (
            rf"고등학생\s*({count_token})\s*명",
            rf"({count_token})\s*명의?\s*고등학생",
        )
    )
    party["middleschool"] = _sum_matches(
        (
            rf"중학생\s*({count_token})\s*명",
            rf"({count_token})\s*명의?\s*중학생",
        )
    )
    party["elementary"] = _sum_matches(
        (
            rf"초등학생\s*({count_token})\s*명",
            rf"({count_token})\s*명의?\s*초등학생",
        )
    )
    party["toddler"] = _sum_matches(
        (
            rf"(?:애기|아기|유아|영아)\s*({count_token})\s*명",
            rf"({count_token})\s*명의?\s*(?:애기|아기|유아|영아)",
        )
    )
    party["adult"] = _sum_matches(
        (
            rf"성인\s*({count_token})\s*명",
            rf"({count_token})\s*명의?\s*성인",
        )
    )

    generic_child_count = _extract_generic_child_count(text)
    if generic_child_count > 0 and (
        party["highschool"]
        + party["middleschool"]
        + party["elementary"]
        + party["toddler"]
    ) == 0:
        party["elementary"] = generic_child_count

    family_members = _count_family_members(text)

    age_kin_map = [
        ("highschool", ("고등학생", "고딩"), ("동생", "형", "누나", "사촌", "조카")),
        ("middleschool", ("중학생", "중딩"), ("동생", "형", "누나", "사촌", "조카")),
        ("elementary", ("초등학생", "초딩"), ("동생", "형", "누나", "사촌", "조카")),
        ("toddler", ("애기", "아기", "유아", "영아"), ("동생", "조카")),
    ]
    knum_pattern = r"(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)"
    for bucket, age_terms, kin_terms in age_kin_map:
        matched = False
        for age_term in age_terms:
            for kin_term in kin_terms:
                base = f"{age_term}{kin_term}"
                count = None
                match = re.search(rf"{base}(\d+)\s*명", text)
                if match:
                    count = int(match.group(1))
                else:
                    match = re.search(rf"{base}{knum_pattern}\s*명", text)
                    if match:
                        count = KOREAN_KNUM_MAP[match.group(1)]

                if base in text:
                    party[bucket] = max(int(party[bucket]), count or 1)
                    family_members = max(0, family_members - (count or 1))
                    matched = True
                    break
            if matched:
                break

    if int(party["adult"]) == 0 and family_members > 0:
        party["adult"] = family_members

    parsed_sum = (
        int(party["adult"])
        + int(party["highschool"])
        + int(party["middleschool"])
        + int(party["elementary"])
        + int(party["toddler"])
    )
    total_people = None

    match = re.search(r"총\s*(\d+)\s*명", text)
    if match:
        total_people = int(match.group(1))

    if total_people is None:
        for token, count in KOREAN_TOTAL_MAP.items():
            if token in text:
                total_people = count
                break

    if total_people is None:
        match = re.search(r"(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*명(?:이서|에서|과|이)?", text)
        if match and not re.search(rf"(?:{KIN_PREFIX_PATTERN}){match.group(1)}\s*명", text):
            total_people = KOREAN_KNUM_MAP[match.group(1)]

    if total_people is None and parsed_sum == 0:
        match = re.search(r"(\d+)\s*명(?:이서|에서|과|이)?", text)
        if match:
            total_people = int(match.group(1))

    if total_people is not None and parsed_sum < total_people:
        party["adult"] += total_people - parsed_sum

    include_speaker = _infer_include_speaker(text)
    if include_speaker and family_members > 0 and total_people is None:
        party["adult"] += 1

    if "혼자" in message or "솔로" in message:
        party["trip_style"] = "solo"
    elif any(token in message for token in ROMANCE_COUPLE_TOKENS):
        party["trip_style"] = "couple"
    elif "친구" in message:
        party["trip_style"] = "friends"
    elif (
        any(token in message for token in FAMILY_TOKENS)
        or "가족" in message
        or any(token in message for token in FILIAL_THEME_TOKENS)
        or generic_child_count > 0
    ):
        party["trip_style"] = "family"

    if party["trip_style"] == "couple" and total_people is None:
        party["adult"] = max(int(party["adult"]), 2)
    elif party["trip_style"] == "friends" and total_people is None:
        if any(token in message for token in ("친구들이랑", "친구들과", "친구들하고")):
            party["adult"] = max(int(party["adult"]), 3)
        elif any(token in message for token in ("친구랑", "친구와", "친구하고")):
            party["adult"] = max(int(party["adult"]), 2)

    if int(party["adult"]) <= 0:
        party["adult"] = 1

    return party
