import re
from typing import Optional

from parser_api.intents import Intent

_CREATE_TOKENS = ("일정", "계획", "코스", "일정표")
_CREATE_VERBS = ("만들", "짜", "추천", "세워", "구성")
_STRONG_MODIFY_TOKENS = (
    "수정",
    "변경",
    "바꿔",
    "업데이트",
    "짠것중",
    "짜놓",
    "기존일정",
    "기존계획",
    "만들어둔일정",
)
_EXPLICIT_MODIFY_TOKENS = (
    "추가",
    "더넣",
    "넣어줘",
    "하나더",
    "더추가",
    "빼줘",
    "제외",
    "삭제",
    "제거",
    "없애",
    "대신",
    "교체",
    "옮겨",
    "이동",
    "스왑",
    "미술관하루",
)
_CONTEXTUAL_MODIFY_TOKENS = (
    "여유롭게",
    "빡세게",
    "줄여",
    "완화",
    "너무많",
    "과해",
    "도보위주",
    "대중교통위주",
    "환승최소",
    "개만",
)
_EXISTING_PLAN_MARKERS = ("짠것중", "짜놓", "기존일정", "기존계획", "만들어둔일정")
_FLIGHT_TOKENS = ("항공권", "비행기표", "flight", "항공", "왕복", "편도", "직항", "항공편")
_HOTEL_TOKENS = ("호텔", "숙소", "hotel", "에어비앤비", "airbnb", "호스텔", "리조트")
_DISCOVERY_VERBS = ("찾", "검색", "알아봐", "구해", "비교", "보여줘", "추천")
_BOOK_VERBS = ("예약", "예매", "book", "발권", "끊어")
_BOOKING_TOKENS = ("예약", "예약번호", "예약 id", "booking", "reservation", "예매")
_BOOKING_LOOKUP_VERBS = ("조회", "확인", "보여", "내역", "상태")
_BOOKING_CHANGE_VERBS = ("변경", "수정", "바꿔", "업데이트")
_BOOKING_CANCEL_VERBS = ("취소", "cancel")
_RECOMMEND_TOKENS = (
    "추천",
    "recommend",
    "명소",
    "관광지",
    "볼거리",
    "가볼만한곳",
    "맛집",
    "식당",
    "레스토랑",
    "카페",
    "restaurant",
    "cafe",
    "attraction",
)
_ROUTE_TOKENS = ("동선", "루트", "경로", "순서", "최적화", "최단", "맵", "route")
_BUDGET_TOKENS = ("예산", "경비", "비용", "얼마", "budget")
_COMPONENT_CONTEXT_TOKENS = ("포함", "제외", "빼고", "합쳐", "만", "기준")
_TRIP_MANAGE_NOUNS = ("일정", "여행일정", "trip", "trips", "plan", "plans")
_TRIP_MANAGE_LIST_TOKENS = ("목록", "리스트", "전체", "모든", "저장한일정", "내일정", "savedtrips", "savedtrip", "list", "show")
_TRIP_MANAGE_SAVE_TOKENS = ("저장", "보관", "save")
_TRIP_MANAGE_RETRIEVE_TOKENS = ("불러", "조회", "열어", "보여줘", "확인", "load", "open")
_TRIP_MANAGE_DELETE_TOKENS = ("삭제", "지워", "없애", "delete", "remove")
_TRIP_MANAGE_RENAME_TOKENS = ("이름", "제목", "rename")
_PROFILE_TOKENS = ("프로필", "내취향", "선호", "내정보", "선호사항")
_PROFILE_UPDATE_TOKENS = ("저장", "업데이트", "설정", "기억", "반영")
_PROFILE_RETRIEVE_TOKENS = ("보여", "조회", "불러", "확인")
_STYLE_TOKENS = ("여행스타일", "스타일분석", "스타일", "취향분석", "어떤스타일")
_STYLE_ANALYZE_TOKENS = ("분석", "진단", "알려", "파악")
_DIARY_TOKENS = ("다이어리", "여행일기", "여행기", "일기", "후기", "기록")
_DIARY_VERBS = ("써", "작성", "남겨", "정리", "생성")


def _compact(message: str) -> str:
    return message.replace(" ", "").lower()


def _looks_like_modify(text: str, context: Optional[dict]) -> bool:
    has_trip_id = bool(
        context and isinstance(context.get("trip_id"), str) and context.get("trip_id")
    )
    if any(token in text for token in _STRONG_MODIFY_TOKENS):
        return True
    if any(token in text for token in _EXPLICIT_MODIFY_TOKENS):
        return True

    has_day_marker = any(
        token in text for token in ("일차", "일째", "번째날", "첫째날", "둘째날", "셋째날")
    )
    return any(token in text for token in _CONTEXTUAL_MODIFY_TOKENS) and (
        has_trip_id or has_day_marker or any(token in text for token in _EXISTING_PLAN_MARKERS)
    )


def _looks_like_create(text: str) -> bool:
    has_plan_noun = any(token in text for token in _CREATE_TOKENS)
    has_plan_verb = any(verb in text for verb in _CREATE_VERBS)
    if has_plan_noun and has_plan_verb:
        return True

    has_trip_context = "여행" in text and any(
        marker in text
        for marker in ("박", "일", "월", "파리", "paris")
    )
    has_trip_verb = any(verb in text for verb in ("만들", "짜", "세워", "구성"))
    return has_trip_context and has_trip_verb


def _looks_like_budget(text: str) -> bool:
    return any(token in text for token in _BUDGET_TOKENS)


def _looks_like_manage_booking(text: str, context: Optional[dict]) -> bool:
    has_booking_ref = bool(
        context
        and any(
            isinstance(context.get(key), str) and context.get(key)
            for key in ("booking_id", "reservation_id")
        )
    )
    has_booking_object = any(token in text for token in _BOOKING_TOKENS)
    has_manage_verb = any(
        token in text
        for token in _BOOKING_LOOKUP_VERBS + _BOOKING_CHANGE_VERBS + _BOOKING_CANCEL_VERBS
    )
    return (has_booking_object and has_manage_verb) or (has_booking_ref and has_manage_verb)


def _has_booking_management_verb(text: str) -> bool:
    return any(
        token in text
        for token in _BOOKING_LOOKUP_VERBS + _BOOKING_CHANGE_VERBS + _BOOKING_CANCEL_VERBS
    )


def _looks_like_flight_book(text: str) -> bool:
    return (
        any(token in text for token in _FLIGHT_TOKENS)
        and any(token in text for token in _BOOK_VERBS)
        and not _has_booking_management_verb(text)
    )


def _looks_like_flight_search(text: str) -> bool:
    has_route = bool(re.search(r"(?:icn|gmp|인천|서울).{0,10}(?:파리|paris|cdg|ory)", text))
    has_search_verb = any(token in text for token in _DISCOVERY_VERBS)
    return (
        (any(token in text for token in _FLIGHT_TOKENS) and has_search_verb)
        or (has_route and any(token in text for token in _FLIGHT_TOKENS) and not _looks_like_flight_book(text))
    ) and not _has_booking_management_verb(text)


def _looks_like_hotel_book(text: str) -> bool:
    return (
        any(token in text for token in _HOTEL_TOKENS)
        and any(token in text for token in _BOOK_VERBS)
        and not _has_booking_management_verb(text)
    )


def _looks_like_hotel_search(text: str) -> bool:
    has_search_verb = any(token in text for token in _DISCOVERY_VERBS)
    has_hotel_modifier = bool(re.search(r"\d성급|star|근처|near", text))
    return (
        any(token in text for token in _HOTEL_TOKENS)
        and ((has_search_verb or has_hotel_modifier) and not _looks_like_hotel_book(text))
        and not _has_booking_management_verb(text)
    )


def _is_component_only_reference(text: str, domain_tokens: tuple[str, ...]) -> bool:
    if not _looks_like_budget(text):
        return False
    if not any(token in text for token in domain_tokens):
        return False
    return any(token in text for token in _COMPONENT_CONTEXT_TOKENS) and not any(
        token in text for token in _DISCOVERY_VERBS + _BOOK_VERBS
    )


def _looks_like_optimize_route(text: str) -> bool:
    return any(token in text for token in _ROUTE_TOKENS) and any(
        token in text for token in ("최적화", "정리", "짤", "추천", "바꿔", "조정", "optimize")
    )


def _looks_like_recommend_venue(text: str) -> bool:
    has_recommend_context = any(token in text for token in _RECOMMEND_TOKENS)
    has_venue = any(
        token in text
        for token in ("맛집", "식당", "레스토랑", "카페", "명소", "관광지", "볼거리", "가볼만한곳", "restaurant", "cafe", "attraction")
    )
    return has_recommend_context and has_venue


def _looks_like_manage_trip(text: str, context: Optional[dict]) -> bool:
    has_trip_ref = bool(
        context and isinstance(context.get("trip_id"), str) and context.get("trip_id")
    )
    has_trip_noun = any(token in text for token in _TRIP_MANAGE_NOUNS)
    has_list = any(token in text for token in _TRIP_MANAGE_LIST_TOKENS)
    has_save = any(token in text for token in _TRIP_MANAGE_SAVE_TOKENS)
    has_retrieve = any(token in text for token in _TRIP_MANAGE_RETRIEVE_TOKENS)
    has_delete = any(token in text for token in _TRIP_MANAGE_DELETE_TOKENS)
    has_rename = any(token in text for token in _TRIP_MANAGE_RENAME_TOKENS) and any(
        token in text for token in ("바꿔", "변경", "수정", "rename")
    )

    if has_trip_noun and (has_list or has_save or has_retrieve or has_delete or has_rename):
        return True

    return has_trip_ref and (has_retrieve or has_delete or has_rename)


def _looks_like_user_profile(text: str) -> bool:
    has_profile_noun = any(token in text for token in _PROFILE_TOKENS)
    has_profile_action = any(token in text for token in _PROFILE_UPDATE_TOKENS + _PROFILE_RETRIEVE_TOKENS)
    return has_profile_noun and has_profile_action


def _looks_like_travel_style(text: str) -> bool:
    has_style_noun = any(token in text for token in _STYLE_TOKENS)
    has_style_action = any(token in text for token in _STYLE_ANALYZE_TOKENS)
    return has_style_noun and has_style_action


def _looks_like_trip_diary(text: str) -> bool:
    return any(token in text for token in _DIARY_TOKENS) and any(
        token in text for token in _DIARY_VERBS
    )


def _first_index(text: str, tokens: tuple[str, ...]) -> int:
    indexes = [text.find(token) for token in tokens if token in text]
    return min(indexes) if indexes else 10**9


def detect_requested_actions(message: str, context: Optional[dict] = None) -> list[Intent]:
    text = _compact(message)
    candidates: list[tuple[int, Intent]] = []

    if _looks_like_manage_booking(text, context):
        candidates.append((_first_index(text, _BOOKING_TOKENS + _BOOKING_LOOKUP_VERBS + _BOOKING_CHANGE_VERBS + _BOOKING_CANCEL_VERBS), Intent.MANAGE_BOOKING))

    if _looks_like_manage_trip(text, context):
        candidates.append((_first_index(text, _TRIP_MANAGE_LIST_TOKENS + _TRIP_MANAGE_SAVE_TOKENS + _TRIP_MANAGE_RETRIEVE_TOKENS + _TRIP_MANAGE_DELETE_TOKENS + _TRIP_MANAGE_RENAME_TOKENS), Intent.MANAGE_TRIP))

    if _looks_like_modify(text, context):
        candidates.append((_first_index(text, _STRONG_MODIFY_TOKENS + _EXPLICIT_MODIFY_TOKENS), Intent.MODIFY_PLAN))
    if _looks_like_create(text):
        candidates.append((_first_index(text, _CREATE_TOKENS), Intent.CREATE_PLAN))

    if _looks_like_flight_book(text) and not _is_component_only_reference(text, _FLIGHT_TOKENS):
        candidates.append((_first_index(text, _FLIGHT_TOKENS), Intent.FLIGHT_BOOK))
    elif _looks_like_flight_search(text) and not _is_component_only_reference(text, _FLIGHT_TOKENS):
        candidates.append((_first_index(text, _FLIGHT_TOKENS), Intent.FLIGHT_SEARCH))

    if _looks_like_hotel_book(text) and not _is_component_only_reference(text, _HOTEL_TOKENS):
        candidates.append((_first_index(text, _HOTEL_TOKENS), Intent.HOTEL_BOOK))
    elif _looks_like_hotel_search(text) and not _is_component_only_reference(text, _HOTEL_TOKENS):
        candidates.append((_first_index(text, _HOTEL_TOKENS), Intent.HOTEL_SEARCH))

    if _looks_like_optimize_route(text):
        candidates.append((_first_index(text, _ROUTE_TOKENS), Intent.OPTIMIZE_ROUTE))

    if _looks_like_recommend_venue(text):
        candidates.append((_first_index(text, _RECOMMEND_TOKENS), Intent.RECOMMEND_VENUE))

    if _looks_like_user_profile(text):
        candidates.append((_first_index(text, _PROFILE_TOKENS), Intent.USER_PROFILE))

    if _looks_like_travel_style(text):
        candidates.append((_first_index(text, _STYLE_TOKENS), Intent.TRAVEL_STYLE))

    if _looks_like_trip_diary(text):
        candidates.append((_first_index(text, _DIARY_TOKENS), Intent.TRIP_DIARY))

    if _looks_like_budget(text):
        candidates.append((_first_index(text, _BUDGET_TOKENS), Intent.ESTIMATE_BUDGET))

    ordered: list[Intent] = []
    for _, intent in sorted(candidates, key=lambda item: item[0]):
        if intent not in ordered:
            ordered.append(intent)
    return ordered


def detect_primary_intent(message: str, context: Optional[dict] = None) -> Intent:
    text = _compact(message)

    actions = detect_requested_actions(message, context)
    if len(actions) >= 2:
        return Intent.REQUEST_BUNDLE
    if actions:
        return actions[0]

    if "cancel" in text or "취소" in text:
        return Intent.CANCEL_PLAN
    return Intent.CREATE_PLAN
