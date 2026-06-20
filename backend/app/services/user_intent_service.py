from __future__ import annotations

import re
import unicodedata
from typing import Any


INTENT_PATTERNS: tuple[dict[str, Any], ...] = (
    {
        "id": "slow_pace",
        "kind": "pace",
        "keywords": ("여유", "느긋", "천천", "slow", "relaxed", "easy"),
        "explicit": "여유로운 속도 선호",
        "hidden": "장소 수와 이동 강도를 낮춰야 함",
    },
    {
        "id": "full_pace",
        "kind": "pace",
        "keywords": ("알차", "빡세", "많이 보고", "많이 가", "많은 장소", "fast", "packed", "full"),
        "explicit": "알찬 일정 선호",
        "hidden": "핵심 명소를 더 촘촘하게 묶어도 됨",
    },
    {
        "id": "romantic",
        "kind": "style",
        "keywords": ("로맨틱", "연인", "커플", "romantic", "couple"),
        "explicit": "로맨틱한 분위기 선호",
        "hidden": "야경, 산책, 저녁 클라이맥스가 중요함",
    },
    {
        "id": "local_mood",
        "kind": "style",
        "keywords": ("현지인", "로컬", "local", "숨은", "골목"),
        "explicit": "현지 감성 선호",
        "hidden": "유명 명소만 나열하기보다 골목, 카페, 동네 산책을 섞어야 함",
    },
    {
        "id": "family_friendly",
        "kind": "companion",
        "keywords": ("가족", "아이", "부모", "family", "kids", "children"),
        "explicit": "가족 동행",
        "hidden": "이동 부담과 대기 시간을 줄이고 가족 친화 장소를 우선해야 함",
    },
    {
        "id": "cafe",
        "kind": "interest",
        "keywords": ("카페", "커피", "디저트", "cafe", "coffee", "dessert"),
        "explicit": "카페/디저트 관심",
        "hidden": "오후 휴식 블록이나 브런치/디저트 경험이 필요함",
    },
    {
        "id": "food",
        "kind": "interest",
        "keywords": ("맛집", "미식", "레스토랑", "프렌치", "food", "restaurant", "french"),
        "explicit": "미식 경험 선호",
        "hidden": "점심/저녁 식사 시간이 자연스럽게 확보되어야 함",
    },
    {
        "id": "museum",
        "kind": "interest",
        "keywords": ("미술관", "박물관", "museum", "gallery"),
        "explicit": "미술관/박물관 관심",
        "hidden": "체류 시간이 긴 실내 관람 블록이 필요함",
    },
    {
        "id": "night_view",
        "kind": "time",
        "keywords": ("야경", "밤", "night", "evening"),
        "explicit": "야경 선호",
        "hidden": "마지막 또는 저녁 시간대에 전망/산책 클라이맥스가 필요함",
    },
    {
        "id": "brunch",
        "kind": "time",
        "keywords": ("브런치", "늦은 아침", "brunch"),
        "explicit": "브런치 선호",
        "hidden": "오전 시작을 무겁게 잡지 않고 식사형 시작점을 둬야 함",
    },
    {
        "id": "late_start",
        "kind": "time",
        "keywords": ("늦게 시작", "천천히 시작", "late start", "start late"),
        "explicit": "늦은 시작 선호",
        "hidden": "오전 9시 이전 시작은 피해야 함",
    },
    {
        "id": "early_start",
        "kind": "time",
        "keywords": ("아침 일찍", "오전부터", "아침부터", "일찍 시작", "early start", "morning start"),
        "explicit": "이른 시작 선호",
        "hidden": "첫 실질 일정이 오전 안에 시작되어야 함",
    },
    {
        "id": "sunset",
        "kind": "time",
        "keywords": ("노을", "석양", "sunset"),
        "explicit": "노을 시간대 선호",
        "hidden": "해질녘 전망/강변 산책 블록이 필요함",
    },
    {
        "id": "famous_sights",
        "kind": "interest",
        "keywords": ("유명 관광지", "랜드마크", "명소", "classic", "landmark", "sightseeing"),
        "explicit": "유명 관광지 관심",
        "hidden": "대표 랜드마크를 최소 하나 이상 포함해야 만족도가 높음",
    },
    {
        "id": "low_walking",
        "kind": "mobility",
        "keywords": ("걷기 싫", "많이 걷", "이동 적", "less walking", "short walk"),
        "explicit": "걷기 부담 최소화",
        "hidden": "가까운 권역 위주로 묶고 고강도 route leg를 줄여야 함",
    },
)


AVOID_PATTERNS: tuple[dict[str, Any], ...] = (
    {
        "id": "avoid_museums",
        "keywords": (
            "미술관 제외",
            "박물관 제외",
            "미술관은 제외",
            "박물관은 제외",
            "미술관 말고",
            "박물관 말고",
            "미술관 빼",
            "박물관 빼",
            "미술관 싫",
            "박물관 싫",
            "미술관은 싫",
            "박물관은 싫",
            "no museum",
            "avoid museum",
        ),
        "explicit": "미술관/박물관 제외",
    },
    {
        "id": "avoid_touristy",
        "keywords": ("관광지 최소", "너무 관광", "touristy", "less touristy"),
        "explicit": "관광지 과밀감 회피",
    },
    {
        "id": "avoid_expensive_restaurants",
        "keywords": ("비싼 식당 제외", "가성비", "저렴", "budget food", "cheap eats"),
        "explicit": "비싼 식당 회피",
    },
    {
        "id": "avoid_long_transfer",
        "keywords": ("먼 이동", "왕복", "이동 많", "long transfer", "far away"),
        "explicit": "긴 이동 회피",
    },
)


def analyze_user_intent(
    *,
    prompt: str = "",
    style_tags: list[str] | tuple[str, ...] | None = None,
    language: str = "ko",
) -> dict[str, Any]:
    """Create parser-facing intent context without turning every nuance into a hard rule."""

    tags = [str(tag).strip() for tag in style_tags or [] if str(tag).strip()]
    source_text = " ".join([str(prompt or ""), *tags]).strip()
    normalized = _normalize(source_text)

    explicit_constraints: list[dict[str, Any]] = []
    hidden_intents: list[dict[str, Any]] = []
    raw_constraints: list[str] = []
    uncertainties: list[str] = []
    detected: dict[str, list[str]] = {
        "styles": [],
        "interests": [],
        "time_preferences": [],
        "avoidances": [],
        "companions": [],
        "mobility": [],
        "pace": [],
    }

    for pattern in INTENT_PATTERNS:
        matched = _matches_any(normalized, pattern["keywords"])
        if not matched:
            continue
        intent_id = str(pattern["id"])
        kind = str(pattern["kind"])
        detected_key = _detected_key(kind)
        detected[detected_key].append(intent_id)
        explicit_constraints.append(
            {
                "id": intent_id,
                "type": kind,
                "label": pattern["explicit"],
                "source": "parser",
                "confidence": 0.82,
            }
        )
        hidden_intents.append(
            {
                "id": intent_id,
                "type": kind,
                "insight": pattern["hidden"],
                "source": "parser_inference",
                "confidence": 0.68,
            }
        )
        raw_constraints.append(str(pattern["explicit"]))

    for pattern in AVOID_PATTERNS:
        if not _matches_any(normalized, pattern["keywords"]):
            continue
        intent_id = str(pattern["id"])
        detected["avoidances"].append(intent_id)
        explicit_constraints.append(
            {
                "id": intent_id,
                "type": "avoidance",
                "label": pattern["explicit"],
                "source": "parser",
                "confidence": 0.86,
            }
        )
        raw_constraints.append(str(pattern["explicit"]))

    if "avoid_museums" in detected["avoidances"] and "museum" in detected["interests"]:
        detected["interests"] = [value for value in detected["interests"] if value != "museum"]
        explicit_constraints = [
            value for value in explicit_constraints if str(value.get("id") or "") != "museum"
        ]
        hidden_intents = [value for value in hidden_intents if str(value.get("id") or "") != "museum"]
        raw_constraints = [value for value in raw_constraints if value != "미술관/박물관 관심"]

    if normalized and not explicit_constraints:
        uncertainties.append("사용자 요청의 취향 단서가 약해 LLM Planner가 원문 맥락을 함께 판단해야 함")
    if "가족" in normalized and "slow_pace" not in detected["pace"]:
        detected["pace"].append("family_adjusted_slow")
        hidden_intents.append(
            {
                "id": "family_adjusted_slow",
                "type": "pace",
                "insight": "가족 동행이므로 pace를 기본보다 조금 느리게 잡는 것이 안전함",
                "source": "parser_inference",
                "confidence": 0.72,
            }
        )

    confidence = _confidence(explicit_constraints, hidden_intents, uncertainties)
    return {
        "source": "parser",
        "language": language,
        "explicit_constraints": explicit_constraints,
        "hidden_intents": hidden_intents,
        "raw_constraints": _unique(raw_constraints),
        "uncertainties": uncertainties,
        "detected_styles": _unique(detected["styles"]),
        "detected_interests": _unique(detected["interests"]),
        "detected_time_preferences": _unique(detected["time_preferences"]),
        "detected_avoidances": _unique(detected["avoidances"]),
        "detected_companions": _unique(detected["companions"]),
        "detected_mobility": _unique(detected["mobility"]),
        "detected_pace": _unique(detected["pace"]),
        "confidence": confidence,
    }


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").lower()
    return re.sub(r"\s+", " ", text).strip()


def _matches_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(_normalize(keyword) in text for keyword in keywords if str(keyword).strip())


def _detected_key(kind: str) -> str:
    if kind == "style":
        return "styles"
    if kind == "interest":
        return "interests"
    if kind == "time":
        return "time_preferences"
    if kind == "companion":
        return "companions"
    if kind == "mobility":
        return "mobility"
    if kind == "pace":
        return "pace"
    return "styles"


def _confidence(
    explicit_constraints: list[dict[str, Any]],
    hidden_intents: list[dict[str, Any]],
    uncertainties: list[str],
) -> float:
    score = 0.35 + min(len(explicit_constraints), 8) * 0.06 + min(len(hidden_intents), 8) * 0.035
    if uncertainties:
        score -= 0.12
    return round(max(0.15, min(score, 0.94)), 2)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value).strip()))
