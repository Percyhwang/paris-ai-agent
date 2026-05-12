from __future__ import annotations

import unittest
from copy import deepcopy
from dataclasses import dataclass
from itertools import product
from unittest.mock import patch

from parser_api.parsers.create_plan.parser import parse_create_plan
from parser_api.parsers.estimate_budget.parser import parse_estimate_budget
from parser_api.parsers.flight_book.parser import parse_flight_book
from parser_api.parsers.flight_search.parser import parse_flight_search
from parser_api.parsers.hotel_book.parser import parse_hotel_book
from parser_api.parsers.hotel_search.parser import parse_hotel_search
from parser_api.parsers.manage_booking.parser import parse_manage_booking
from parser_api.parsers.manage_trip.parser import parse_manage_trip
from parser_api.parsers.modify_plan.parser import parse_modify_plan
from parser_api.parsers.optimize_route.parser import parse_optimize_route
from parser_api.parsers.recommend_venue.parser import parse_recommend_venue
from parser_api.parsers.travel_style.parser import parse_travel_style
from parser_api.parsers.trip_diary.parser import parse_trip_diary
from parser_api.parsers.user_profile.parser import parse_user_profile
from parser_api.parsers.workflow.request_bundle.parser import parse_request_bundle
from parser_api.parsers.workflow.shared_context.parser import parse_shared_context


@dataclass(frozen=True)
class ParserCase:
    name: str
    message: str
    expected: dict
    context: dict | None = None


def _assert_subset(test_case: unittest.TestCase, actual, expected) -> None:
    if isinstance(expected, dict):
        test_case.assertIsInstance(actual, dict)
        for key, value in expected.items():
            test_case.assertIn(key, actual)
            _assert_subset(test_case, actual[key], value)
        return

    if isinstance(expected, list):
        test_case.assertIsInstance(actual, list)
        if all(not isinstance(item, dict) for item in expected):
            for expected_item in expected:
                test_case.assertIn(expected_item, actual)
            return

        test_case.assertGreaterEqual(len(actual), len(expected))
        for actual_item, expected_item in zip(actual, expected):
            _assert_subset(test_case, actual_item, expected_item)
        return

    test_case.assertEqual(actual, expected)


def _merge_dicts(*parts: dict) -> dict:
    merged: dict = {}
    for part in parts:
        for key, value in part.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = _merge_dicts(merged[key], value)
            else:
                merged[key] = deepcopy(value)
    return merged


def _expect_actions(*intents: str) -> dict:
    return {
        "actions": [
            {"intent": intent, "order": index + 1}
            for index, intent in enumerate(intents)
        ]
    }


def _shared_context_cases() -> list[ParserCase]:
    date_specs = [
        ("d1", "7월 10일", {"dates": {"start_date": "2026-07-10", "source": "explicit"}}),
        ("d2", "2026년 7월 10일", {"dates": {"start_date": "2026-07-10", "source": "explicit"}}),
        (
            "d3",
            "7월 10일부터 7월 14일까지",
            {
                "dates": {
                    "start_date": "2026-07-10",
                    "end_date": "2026-07-14",
                    "days": 5,
                    "source": "explicit",
                }
            },
        ),
        (
            "d4",
            "7월 10일~14일",
            {
                "dates": {
                    "start_date": "2026-07-10",
                    "end_date": "2026-07-14",
                    "days": 5,
                    "source": "explicit",
                }
            },
        ),
        ("d5", "3박4일", {"dates": {"days": 4, "source": "explicit"}}),
    ]
    route_specs = [
        (
            "r1",
            "인천에서 파리 가는",
            {
                "origin": {"city": "Incheon", "airport_code": "ICN"},
                "destination": {"city": "Paris", "country": "FR"},
            },
        ),
        (
            "r2",
            "서울에서 파리 여행",
            {
                "origin": {"city": "Seoul", "country": "KR"},
                "destination": {"city": "Paris", "country": "FR"},
            },
        ),
        (
            "r3",
            "icn-cdg",
            {
                "origin": {"city": "Incheon", "airport_code": "ICN"},
                "destination": {"city": "Paris", "airport_code": "CDG"},
            },
        ),
        (
            "r4",
            "김포에서 파리로 떠나는",
            {
                "origin": {"city": "Seoul", "airport_code": "GMP"},
                "destination": {"city": "Paris", "country": "FR"},
            },
        ),
        ("r5", "파리 여행", {"destination": {"city": "Paris", "country": "FR"}}),
    ]
    party_specs = [
        ("p1", "성인 2명", {"party": {"adult": 2}}),
        ("p2", "친구 3명이서", {"party": {"adult": 3, "trip_style": "friends"}}),
        (
            "p3",
            "가족여행 아이 1명",
            {"party": {"adult": 1, "elementary": 1, "trip_style": "family"}},
        ),
    ]
    budget_specs = [
        ("b1", "예산은 300만원으로", {"budget": {"budget_total": 3000000, "currency": "KRW"}}),
        (
            "b2",
            "하루 20만원 정도로 가성비 있게",
            {"budget": {"budget_per_day": 200000, "budget_mode": "save", "currency": "KRW"}},
        ),
    ]

    cases: list[ParserCase] = []
    for date_spec, route_spec, party_spec, budget_spec in product(
        date_specs,
        route_specs,
        party_specs,
        budget_specs,
    ):
        date_name, date_text, date_expected = date_spec
        route_name, route_text, route_expected = route_spec
        party_name, party_text, party_expected = party_spec
        budget_name, budget_text, budget_expected = budget_spec
        message = f"{date_text} {route_text} {party_text} 여행 {budget_text} 정리해줘"
        expected = _merge_dicts(date_expected, route_expected, party_expected, budget_expected)
        cases.append(
            ParserCase(
                name=f"{date_name}_{route_name}_{party_name}_{budget_name}",
                message=message,
                expected=expected,
            )
        )
    return cases


def _request_bundle_cases() -> list[ParserCase]:
    pair_specs = [
        ("bundle_01", "파리 3박4일 일정 짜줘", "예산도 계산해줘", ("CREATE_PLAN", "ESTIMATE_BUDGET"), None),
        (
            "bundle_02",
            "7월 10일 인천에서 파리 가는 왕복 항공권 찾아줘",
            "에펠탑 근처 4성급 호텔도 찾아줘",
            ("FLIGHT_SEARCH", "HOTEL_SEARCH"),
            None,
        ),
        (
            "bundle_03",
            "7월 10일 인천에서 파리 가는 항공권 예약해줘",
            "에펠탑 근처 호텔도 예약해줘",
            ("FLIGHT_BOOK", "HOTEL_BOOK"),
            None,
        ),
        (
            "bundle_04",
            "파리 맛집 추천해줘",
            "루브르, 오르세, 에펠탑 동선 최적화해줘",
            ("RECOMMEND_VENUE", "OPTIMIZE_ROUTE"),
            None,
        ),
        (
            "bundle_05",
            "저장한 일정 목록 보여줘",
            "2일차 여행 일기 써줘",
            ("MANAGE_TRIP", "TRIP_DIARY"),
            None,
        ),
        (
            "bundle_06",
            "내 여행 프로필 저장해줘",
            "여행 스타일 분석해줘",
            ("USER_PROFILE", "TRAVEL_STYLE"),
            None,
        ),
        (
            "bundle_07",
            "호텔 예약 취소해줘",
            "남은 예산도 계산해줘",
            ("MANAGE_BOOKING", "ESTIMATE_BUDGET"),
            {"booking_id": "bk_ctx_bundle"},
        ),
        (
            "bundle_08",
            "파리 4일 일정 짜줘",
            "카페도 추천해줘",
            ("CREATE_PLAN", "RECOMMEND_VENUE"),
            None,
        ),
        (
            "bundle_09",
            "2일차 오후 루브르 빼줘",
            "동선도 다시 최적화해줘",
            ("MODIFY_PLAN", "OPTIMIZE_ROUTE"),
            {"trip_id": "trip-bundle-09"},
        ),
        (
            "bundle_10",
            "에펠탑 근처 4성급 호텔 찾아줘",
            "근처 카페도 추천해줘",
            ("HOTEL_SEARCH", "RECOMMEND_VENUE"),
            None,
        ),
        (
            "bundle_11",
            "7월 10일 인천에서 파리 가는 항공권 찾아줘",
            "호텔도 찾아주고 예산도 계산해줘",
            ("FLIGHT_SEARCH", "HOTEL_SEARCH", "ESTIMATE_BUDGET"),
            None,
        ),
        (
            "bundle_12",
            "현재 일정 저장해줘",
            "내 여행 프로필도 보여줘",
            ("MANAGE_TRIP", "USER_PROFILE"),
            {"trip_id": "trip-bundle-12"},
        ),
        (
            "bundle_13",
            "항공권 예약 조회해줘",
            "2일차 여행 일기도 써줘",
            ("MANAGE_BOOKING", "TRIP_DIARY"),
            {"booking_id": "bk_ctx_bundle_13"},
        ),
        (
            "bundle_14",
            "파리 3박4일 일정 짜줘",
            "항공권이랑 호텔도 찾아줘",
            ("CREATE_PLAN", "FLIGHT_SEARCH", "HOTEL_SEARCH"),
            None,
        ),
        (
            "bundle_15",
            "내 여행 프로필 저장해줘",
            "파리 맛집도 추천해줘",
            ("USER_PROFILE", "RECOMMEND_VENUE"),
            None,
        ),
    ]
    joiners = [
        ("j1", "{a} 그리고 {b}"),
        ("j2", "{a}. {b}"),
        ("j3", "{a} 같이 {b}"),
        ("j4", "{a} 이어서 {b}"),
        ("j5", "{a} 하고 {b}"),
        ("j6", "{a} 다음으로 {b}"),
        ("j7", "{a} 또 {b}"),
        ("j8", "{a} 한 번에 {b}"),
        ("j9", "{a} 먼저 하고 {b}"),
        ("j10", "{a} 부탁하고 {b}"),
    ]

    cases: list[ParserCase] = []
    for pair_name, first, second, intents, context in pair_specs:
        for joiner_name, template in joiners:
            message = template.format(a=first, b=second)
            cases.append(
                ParserCase(
                    name=f"{pair_name}_{joiner_name}",
                    message=message,
                    expected=_expect_actions(*intents),
                    context=context,
                )
            )
    return cases


def _create_plan_cases() -> list[ParserCase]:
    date_specs = [
        ("d1", "파리 3박4일", {"dates": {"days": 4, "source": "explicit"}}),
        ("d2", "파리 4일", {"dates": {"days": 4, "source": "explicit"}}),
        (
            "d3",
            "7월 10일부터 7월 14일까지 파리",
            {
                "dates": {
                    "start_date": "2026-07-10",
                    "end_date": "2026-07-14",
                    "days": 5,
                    "source": "explicit",
                }
            },
        ),
        (
            "d4",
            "7월 10일~14일 파리",
            {
                "dates": {
                    "start_date": "2026-07-10",
                    "end_date": "2026-07-14",
                    "days": 5,
                    "source": "explicit",
                }
            },
        ),
        (
            "d5",
            "2026년 7월 10일~2026년 7월 14일 파리",
            {
                "dates": {
                    "start_date": "2026-07-10",
                    "end_date": "2026-07-14",
                    "days": 5,
                    "source": "explicit",
                }
            },
        ),
    ]
    party_specs = [
        ("p1", "혼자", {"party": {"adult": 1, "trip_style": "solo"}}),
        ("p2", "커플", {"party": {"adult": 2, "trip_style": "couple"}}),
        ("p3", "친구 3명이서", {"party": {"adult": 3, "trip_style": "friends"}}),
        (
            "p4",
            "가족여행 아이 1명",
            {"party": {"adult": 1, "elementary": 1, "trip_style": "family"}},
        ),
        ("p5", "성인 2명", {"party": {"adult": 2}}),
    ]
    modifier_specs = [
        ("m1", "도보 위주로", {"mobility": {"travel_mode": "walk"}}),
        ("m2", "대중교통 위주로", {"mobility": {"travel_mode": "transit"}}),
        ("m3", "카페 많이 가고", {"preferences": {"weights": {"cafe": 0.8}}}),
        ("m4", "에펠탑은 꼭 넣고", {"preferences": {"must_include": ["에펠탑"]}}),
        ("m5", "루브르는 빼줘", {"preferences": {"must_avoid": ["루브르"]}}),
        ("m6", "비 오면 대체 일정도 같이", {"constraints": {"rainy_plan": True}}),
    ]

    cases: list[ParserCase] = []
    for date_spec, party_spec, modifier_spec in product(
        date_specs,
        party_specs,
        modifier_specs,
    ):
        date_name, date_text, date_expected = date_spec
        party_name, party_text, party_expected = party_spec
        modifier_name, modifier_text, modifier_expected = modifier_spec
        message = f"{party_text} {date_text} 여행 {modifier_text} 계획 세워줘"
        expected = _merge_dicts(
            {"clarify": {"needed": False}},
            date_expected,
            party_expected,
            modifier_expected,
        )
        cases.append(
            ParserCase(
                name=f"{date_name}_{party_name}_{modifier_name}",
                message=message,
                expected=expected,
            )
        )
    return cases


def _modify_plan_cases() -> list[ParserCase]:
    day_specs = [
        ("d1", "1일차", {"operations": [{"target_day": 1}]}),
        ("d2", "2일차", {"operations": [{"target_day": 2}]}),
        ("d3", "3일차", {"operations": [{"target_day": 3}]}),
        ("d4", "4일차", {"operations": [{"target_day": 4}]}),
        ("d5", "5일차", {"operations": [{"target_day": 5}]}),
    ]
    op_specs = [
        (
            "o1",
            "오후에 에펠탑 추가해줘",
            {"operations": [{"op": "add", "target_slot": "afternoon", "place_name": "에펠탑"}]},
        ),
        (
            "o2",
            "오후에 루브르 빼줘",
            {"operations": [{"op": "remove", "target_slot": "afternoon", "place_name": "루브르"}]},
        ),
        (
            "o3",
            "오후에 루브르 대신 오르세로 바꿔줘",
            {
                "operations": [
                    {
                        "op": "replace",
                        "target_slot": "afternoon",
                        "place_name": "루브르",
                        "constraints_patch": {
                            "replace_mode": "place_to_place",
                            "from_place": "루브르",
                            "to_place": "오르세",
                        },
                    }
                ]
            },
        ),
        (
            "o4",
            "오전이랑 오후 바꿔줘",
            {"operations": [{"op": "swap", "swap_slots": ["morning", "afternoon"]}]},
        ),
        ("o5", "너무 빡세니까 여유롭게 바꿔줘", {"operations": [{"op": "set_pace", "pace": "slow"}]}),
        (
            "o6",
            "도보 위주로 바꿔줘",
            {"operations": [{"op": "set_mobility", "mobility": {"travel_mode": "walk"}}]},
        ),
    ]
    wrappers = [
        ("w1", "{day} {op}"),
        ("w2", "{day} 일정에서 {op}"),
        ("w3", "현재 일정 {day} {op}"),
        ("w4", "trip-123 {day} {op}"),
        ("w5", "{day} 코스 {op}"),
    ]
    context = {"trip_id": "trip-123"}

    cases: list[ParserCase] = []
    for day_spec, op_spec, wrapper in product(day_specs, op_specs, wrappers):
        day_name, day_text, day_expected = day_spec
        op_name, op_text, op_expected = op_spec
        wrapper_name, wrapper_template = wrapper
        message = wrapper_template.format(day=day_text, op=op_text)
        expected = _merge_dicts(
            {"trip_id": "trip-123", "clarify": {"needed": False}},
            day_expected,
            op_expected,
        )
        cases.append(
            ParserCase(
                name=f"{day_name}_{op_name}_{wrapper_name}",
                message=message,
                expected=expected,
                context=context,
            )
        )
    return cases


def _flight_search_cases() -> list[ParserCase]:
    date_specs = [
        ("d1", "7월 10일", {"departure_date": "2026-07-10"}),
        ("d2", "2026년 7월 10일", {"departure_date": "2026-07-10"}),
        (
            "d3",
            "7월 10일부터 7월 14일까지",
            {"departure_date": "2026-07-10", "return_date": "2026-07-14"},
        ),
        ("d4", "7월 10일~14일", {"departure_date": "2026-07-10", "return_date": "2026-07-14"}),
        ("d5", "7월 10일 출발", {"departure_date": "2026-07-10"}),
    ]
    route_specs = [
        (
            "r1",
            "인천에서 파리 가는",
            {"origin": {"airport_code": "ICN"}, "destination": {"city": "Paris"}},
        ),
        (
            "r2",
            "서울에서 파리 가는",
            {"origin": {"city": "Seoul"}, "destination": {"city": "Paris"}},
        ),
        (
            "r3",
            "icn-cdg",
            {"origin": {"airport_code": "ICN"}, "destination": {"airport_code": "CDG", "city": "Paris"}},
        ),
        (
            "r4",
            "김포에서 파리 가는",
            {"origin": {"airport_code": "GMP"}, "destination": {"city": "Paris"}},
        ),
        (
            "r5",
            "인천에서 paris 가는",
            {"origin": {"airport_code": "ICN"}, "destination": {"city": "Paris"}},
        ),
    ]
    option_specs = [
        ("o1", "왕복 직항 비즈니스석 항공권 찾아줘", {"trip_type": "round_trip", "direct_only": True, "cabin_class": "business"}),
        ("o2", "편도 이코노미 항공권 찾아줘", {"trip_type": "one_way", "cabin_class": "economy"}),
        ("o3", "왕복 퍼스트 항공편 검색해줘", {"trip_type": "round_trip", "cabin_class": "first"}),
        ("o4", "왕복 프리미엄이코노미 항공권 비교해줘", {"trip_type": "round_trip", "cabin_class": "premium_economy"}),
        ("o5", "직항 항공권 120만원 이하로 찾아줘", {"direct_only": True, "max_price": 1200000, "currency": "KRW"}),
        ("o6", "왕복 비즈니스석 항공권은 250만원 이하로 찾아줘", {"trip_type": "round_trip", "cabin_class": "business", "max_price": 2500000, "currency": "KRW"}),
    ]

    cases: list[ParserCase] = []
    for date_spec, route_spec, option_spec in product(
        date_specs,
        route_specs,
        option_specs,
    ):
        date_name, date_text, date_expected = date_spec
        route_name, route_text, route_expected = route_spec
        option_name, option_text, option_expected = option_spec
        message = f"{date_text} {route_text} {option_text}"
        expected = _merge_dicts(
            {"clarify": {"needed": False}},
            date_expected,
            route_expected,
            option_expected,
        )
        cases.append(
            ParserCase(
                name=f"{date_name}_{route_name}_{option_name}",
                message=message,
                expected=expected,
            )
        )
    return cases


def _hotel_search_cases() -> list[ParserCase]:
    date_specs = [
        ("d1", "7월 10일 체크인", {"check_in_date": "2026-07-10"}),
        ("d2", "2026년 7월 10일 체크인", {"check_in_date": "2026-07-10"}),
        (
            "d3",
            "7월 10일부터 7월 14일까지",
            {"check_in_date": "2026-07-10", "check_out_date": "2026-07-14", "nights": 4},
        ),
        ("d4", "7월 10일~14일", {"check_in_date": "2026-07-10", "check_out_date": "2026-07-14", "nights": 4}),
        ("d5", "3박4일", {"nights": 3}),
    ]
    landmark_specs = [
        ("l1", "에펠탑 근처", {"area": "near_eiffel_tower", "landmark": "eiffel_tower"}),
        ("l2", "루브르 근처", {"area": "near_louvre", "landmark": "louvre"}),
        ("l3", "오르세 근처", {"area": "near_orsay", "landmark": "orsay"}),
        ("l4", "샹젤리제 근처", {"area": "near_champs_elysees", "landmark": "champs_elysees"}),
        ("l5", "몽마르트 근처", {"area": "near_montmartre", "landmark": "montmartre"}),
    ]
    option_specs = [
        ("o1", "4성급 호텔 찾아줘", {"star_rating": 4}),
        ("o2", "5성급 숙소 찾아줘", {"star_rating": 5}),
        ("o3", "성인 2명 방 2개 호텔 찾아줘", {"guests": 2, "rooms": 2}),
        ("o4", "성인 3명 객실 1개 호텔 찾아줘", {"guests": 3, "rooms": 1}),
        ("o5", "1박 25만원 이하 호텔 찾아줘", {"max_price_per_night": 250000, "currency": "KRW"}),
        ("o6", "4성급 호텔 성인 2명 방 2개 1박 30만원 이하로 찾아줘", {"star_rating": 4, "guests": 2, "rooms": 2, "max_price_per_night": 300000, "currency": "KRW"}),
    ]

    cases: list[ParserCase] = []
    for date_spec, landmark_spec, option_spec in product(
        date_specs,
        landmark_specs,
        option_specs,
    ):
        date_name, date_text, date_expected = date_spec
        landmark_name, landmark_text, landmark_expected = landmark_spec
        option_name, option_text, option_expected = option_spec
        message = f"{date_text} 파리 {landmark_text} {option_text}"
        expected = _merge_dicts(
            {"destination": {"city": "Paris"}, "clarify": {"needed": False}},
            date_expected,
            landmark_expected,
            option_expected,
        )
        cases.append(
            ParserCase(
                name=f"{date_name}_{landmark_name}_{option_name}",
                message=message,
                expected=expected,
            )
        )
    return cases


def _estimate_budget_cases() -> list[ParserCase]:
    trip_specs = [
        ("t1", "파리 3박4일 여행", {"destination": {"city": "Paris"}, "dates": {"days": 4}}),
        ("t2", "파리 4일 여행", {"destination": {"city": "Paris"}, "dates": {"days": 4}}),
        (
            "t3",
            "7월 10일부터 7월 14일까지 파리 여행",
            {"destination": {"city": "Paris"}, "dates": {"start_date": "2026-07-10", "end_date": "2026-07-14", "days": 5}},
        ),
        (
            "t4",
            "2026년 7월 10일~2026년 7월 14일 파리 여행",
            {"destination": {"city": "Paris"}, "dates": {"start_date": "2026-07-10", "end_date": "2026-07-14", "days": 5}},
        ),
        (
            "t5",
            "7월 10일~14일 파리 여행",
            {"destination": {"city": "Paris"}, "dates": {"start_date": "2026-07-10", "end_date": "2026-07-14", "days": 5}},
        ),
    ]
    component_specs = [
        (
            "c1",
            "예산 계산해줘. 항공권, 호텔, 식비만 포함해줘",
            {"components": {"flight": True, "hotel": True, "food": True, "transport": False, "activities": False, "shopping": False}},
        ),
        (
            "c2",
            "예산 계산해줘. 교통이랑 액티비티만 포함해줘",
            {"components": {"flight": False, "hotel": False, "food": False, "transport": True, "activities": True, "shopping": False}},
        ),
        (
            "c3",
            "예산 계산해줘. 쇼핑 제외하고 다 포함해줘",
            {"components": {"flight": True, "hotel": True, "food": True, "transport": True, "activities": True, "shopping": False}},
        ),
        (
            "c4",
            "예산 계산해줘. 항공권 빼고 호텔, 식비, 교통 포함해줘",
            {"components": {"flight": False, "hotel": True, "food": True, "transport": True, "activities": False, "shopping": False}},
        ),
        (
            "c5",
            "예산 계산해줘",
            {"components": {"flight": True, "hotel": True, "food": True, "transport": True, "activities": True, "shopping": False}},
        ),
    ]
    extra_specs = [
        ("e1", "성인 2명 기준으로", {"party": {"adult": 2}}),
        ("e2", "친구 3명이서 가성비로", {"party": {"adult": 3, "trip_style": "friends"}, "budget": {"budget_mode": "save"}}),
        ("e3", "가족여행 아이 1명 포함", {"party": {"adult": 1, "elementary": 1, "trip_style": "family"}}),
        ("e4", "총예산 400만원으로", {"budget": {"budget_total": 4000000}}),
        ("e5", "하루 25만원 정도로", {"budget": {"budget_per_day": 250000}}),
        ("e6", "4성급 호텔 기준으로", {"hotel_star_rating": 4}),
    ]

    cases: list[ParserCase] = []
    for trip_spec, component_spec, extra_spec in product(
        trip_specs,
        component_specs,
        extra_specs,
    ):
        trip_name, trip_text, trip_expected = trip_spec
        component_name, component_text, component_expected = component_spec
        extra_name, extra_text, extra_expected = extra_spec
        message = f"{trip_text} {extra_text} {component_text}"
        expected = _merge_dicts(
            {"clarify": {"needed": False}},
            trip_expected,
            component_expected,
            extra_expected,
        )
        cases.append(
            ParserCase(
                name=f"{trip_name}_{component_name}_{extra_name}",
                message=message,
                expected=expected,
            )
        )
    return cases


def _flight_book_cases() -> list[ParserCase]:
    date_specs = [
        ("d1", "7월 10일", {"departure_date": "2026-07-10"}),
        ("d2", "2026년 7월 10일", {"departure_date": "2026-07-10"}),
        ("d3", "7월 10일부터 7월 14일까지", {"departure_date": "2026-07-10", "return_date": "2026-07-14"}),
        ("d4", "7월 10일~14일", {"departure_date": "2026-07-10", "return_date": "2026-07-14"}),
        ("d5", "7월 10일 출발", {"departure_date": "2026-07-10"}),
    ]
    route_specs = [
        ("r1", "인천에서 파리 가는", {"origin": {"airport_code": "ICN"}, "destination": {"city": "Paris"}}),
        ("r2", "서울에서 파리 가는", {"origin": {"city": "Seoul"}, "destination": {"city": "Paris"}}),
        ("r3", "icn-cdg", {"origin": {"airport_code": "ICN"}, "destination": {"airport_code": "CDG", "city": "Paris"}}),
        ("r4", "김포에서 파리 가는", {"origin": {"airport_code": "GMP"}, "destination": {"city": "Paris"}}),
        ("r5", "인천에서 paris 가는", {"origin": {"airport_code": "ICN"}, "destination": {"city": "Paris"}}),
    ]
    option_specs = [
        ("o1", "왕복 직항 비즈니스석 항공권 예약해줘", {"trip_type": "round_trip", "direct_only": True, "cabin_class": "business", "offer_ref": "flt_ctx_01"}, {"offer_ref": "flt_ctx_01"}),
        ("o2", "편도 이코노미 항공권 예약해줘", {"trip_type": "one_way", "cabin_class": "economy", "offer_ref": "flt_ctx_02"}, {"offer_ref": "flt_ctx_02"}),
        ("o3", "왕복 퍼스트 항공권 offer:FLT900 예약해줘", {"trip_type": "round_trip", "cabin_class": "first", "offer_ref": "FLT900"}, None),
        ("o4", "왕복 프리미엄이코노미 항공권 옵션#FLT901 예약해줘", {"trip_type": "round_trip", "cabin_class": "premium_economy", "offer_ref": "FLT901"}, None),
        ("o5", "직항 항공권 120만원 이하로 예약해줘", {"direct_only": True, "max_price": 1200000, "currency": "KRW", "offer_ref": "flt_ctx_05"}, {"offer_ref": "flt_ctx_05"}),
        ("o6", "왕복 비즈니스석 항공권 offer:FLT902 250만원 이하로 예약해줘", {"trip_type": "round_trip", "cabin_class": "business", "max_price": 2500000, "currency": "KRW", "offer_ref": "FLT902"}, None),
    ]

    cases: list[ParserCase] = []
    for date_spec, route_spec, option_spec in product(
        date_specs,
        route_specs,
        option_specs,
    ):
        date_name, date_text, date_expected = date_spec
        route_name, route_text, route_expected = route_spec
        option_name, option_text, option_expected, option_context = option_spec
        message = f"{date_text} {route_text} {option_text}"
        expected = _merge_dicts(
            {"clarify": {"needed": False}, "requires_confirmation": True},
            date_expected,
            route_expected,
            option_expected,
        )
        cases.append(
            ParserCase(
                name=f"{date_name}_{route_name}_{option_name}",
                message=message,
                expected=expected,
                context=option_context,
            )
        )
    return cases


def _hotel_book_cases() -> list[ParserCase]:
    date_specs = [
        ("d1", "7월 10일 체크인", {"check_in_date": "2026-07-10"}),
        ("d2", "2026년 7월 10일 체크인", {"check_in_date": "2026-07-10"}),
        ("d3", "7월 10일부터 7월 14일까지", {"check_in_date": "2026-07-10", "check_out_date": "2026-07-14", "nights": 4}),
        ("d4", "7월 10일~14일", {"check_in_date": "2026-07-10", "check_out_date": "2026-07-14", "nights": 4}),
        ("d5", "3박4일", {"nights": 3}),
    ]
    landmark_specs = [
        ("l1", "에펠탑 근처", {"area": "near_eiffel_tower", "landmark": "eiffel_tower"}),
        ("l2", "루브르 근처", {"area": "near_louvre", "landmark": "louvre"}),
        ("l3", "오르세 근처", {"area": "near_orsay", "landmark": "orsay"}),
        ("l4", "샹젤리제 근처", {"area": "near_champs_elysees", "landmark": "champs_elysees"}),
        ("l5", "몽마르트 근처", {"area": "near_montmartre", "landmark": "montmartre"}),
    ]
    option_specs = [
        ("o1", "4성급 호텔 예약해줘", {"star_rating": 4, "property_ref": "hotel_ctx_01"}, {"property_ref": "hotel_ctx_01"}),
        ("o2", "5성급 숙소 예약해줘", {"star_rating": 5, "property_ref": "hotel_ctx_02"}, {"property_ref": "hotel_ctx_02"}),
        ("o3", "성인 2명 방 2개 호텔 옵션:HOTEL900 예약해줘", {"guests": 2, "rooms": 2, "property_ref": "HOTEL900"}, None),
        ("o4", "성인 3명 객실 1개 호텔 property#HOTEL901 예약해줘", {"guests": 3, "rooms": 1, "property_ref": "HOTEL901"}, None),
        ("o5", "1박 25만원 이하 호텔 예약해줘", {"max_price_per_night": 250000, "currency": "KRW", "property_ref": "hotel_ctx_05"}, {"property_ref": "hotel_ctx_05"}),
        ("o6", "4성급 호텔 성인 2명 방 2개 1박 30만원 이하로 예약해줘", {"star_rating": 4, "guests": 2, "rooms": 2, "max_price_per_night": 300000, "currency": "KRW", "property_ref": "hotel_ctx_06"}, {"property_ref": "hotel_ctx_06"}),
    ]

    cases: list[ParserCase] = []
    for date_spec, landmark_spec, option_spec in product(
        date_specs,
        landmark_specs,
        option_specs,
    ):
        date_name, date_text, date_expected = date_spec
        landmark_name, landmark_text, landmark_expected = landmark_spec
        option_name, option_text, option_expected, option_context = option_spec
        message = f"{date_text} 파리 {landmark_text} {option_text}"
        expected = _merge_dicts(
            {"destination": {"city": "Paris"}, "clarify": {"needed": False}, "requires_confirmation": True},
            date_expected,
            landmark_expected,
            option_expected,
        )
        cases.append(
            ParserCase(
                name=f"{date_name}_{landmark_name}_{option_name}",
                message=message,
                expected=expected,
                context=option_context,
            )
        )
    return cases


def _manage_booking_cases() -> list[ParserCase]:
    id_specs = [
        ("i1", "", "BKCTX001", {"booking_id": "BKCTX001"}),
        ("i2", "예약번호:BK100", "BK100", None),
        ("i3", "예약번호 BK101", "BK101", None),
        ("i4", "booking:BK102", "BK102", None),
        ("i5", "reservation BK103", "BK103", None),
    ]
    operation_specs = [
        ("o1", "예약 조회해줘", {"operation": "retrieve", "clarify": {"needed": False}}),
        ("o2", "예약 취소해줘", {"operation": "cancel", "requires_confirmation": True, "clarify": {"needed": False}}),
        (
            "o3",
            "예약 날짜를 7월 12일부터 7월 15일까지로 변경해줘",
            {
                "operation": "modify",
                "change_request": {
                    "check_in_date": "2026-07-12",
                    "check_out_date": "2026-07-15",
                    "departure_date": "2026-07-12",
                    "return_date": "2026-07-15",
                },
                "clarify": {"needed": False},
            },
        ),
        (
            "o4",
            "예약 인원을 성인 3명으로 변경해줘",
            {"operation": "modify", "change_request": {"guests": 3}, "clarify": {"needed": False}},
        ),
        (
            "o5",
            "예약 객실 2개로 바꿔줘",
            {"operation": "modify", "change_request": {"rooms": 2}, "clarify": {"needed": False}},
        ),
    ]
    domain_specs = [
        ("d1", "항공권", {"booking_domain": "flight"}),
        ("d2", "비행기", {"booking_domain": "flight"}),
        ("d3", "호텔", {"booking_domain": "hotel"}),
        ("d4", "숙소", {"booking_domain": "hotel"}),
        ("d5", "항공권이랑 호텔", {"booking_domain": "mixed"}),
        ("d6", "", {"booking_domain": "unknown"}),
    ]

    cases: list[ParserCase] = []
    for id_spec, operation_spec, domain_spec in product(
        id_specs,
        operation_specs,
        domain_specs,
    ):
        id_name, id_text, booking_id, id_context = id_spec
        operation_name, operation_text, operation_expected = operation_spec
        domain_name, domain_text, domain_expected = domain_spec
        context = deepcopy(id_context) if id_context else None
        parts = [part for part in (domain_text, id_text, operation_text) if part]
        message = " ".join(parts)
        expected = _merge_dicts(
            {"booking_id": booking_id},
            domain_expected,
            operation_expected,
        )
        cases.append(
            ParserCase(
                name=f"{id_name}_{operation_name}_{domain_name}",
                message=message,
                expected=expected,
                context=context,
            )
        )
    return cases


def _optimize_route_cases() -> list[ParserCase]:
    point_specs = [
        ("p1", "루브르, 오르세, 에펠탑", {"route_points": [{"name": "루브르"}, {"name": "오르세"}, {"name": "에펠탑"}]}),
        ("p2", "에펠탑, 개선문, 몽마르트", {"route_points": [{"name": "에펠탑"}, {"name": "개선문"}, {"name": "몽마르트"}]}),
        ("p3", "노트르담, 루브르, 베르사유", {"route_points": [{"name": "루브르"}, {"name": "노트르담"}, {"name": "베르사유"}]}),
        ("p4", "몽마르트, 오르세, 개선문", {"route_points": [{"name": "오르세"}, {"name": "개선문"}, {"name": "몽마르트"}]}),
        ("p5", "베르사유, 에펠탑, 루브르", {"route_points": [{"name": "루브르"}, {"name": "에펠탑"}, {"name": "베르사유"}]}),
    ]
    mode_specs = [
        ("m1", "대중교통 위주로 동선 최적화해줘", {"travel_mode": "transit", "optimize": "min_time"}),
        ("m2", "도보 위주로 동선 최적화해줘", {"travel_mode": "walk", "optimize": "min_time"}),
        ("m3", "환승 최소로 동선 최적화해줘", {"travel_mode": "both", "optimize": "min_transfers"}),
        ("m4", "거리 최소로 동선 최적화해줘", {"travel_mode": "both", "optimize": "min_distance"}),
        ("m5", "걷기 최소로 동선 최적화해줘", {"travel_mode": "both", "optimize": "min_walking"}),
    ]
    wrapper_specs = [
        ("w1", "{points} {mode}", {}, None),
        ("w2", "2일차 {points} {mode}", {"target_day": 2}, None),
        ("w3", "서울에서 시작해서 {points} {mode}", {"start_location": {"city": "Seoul"}}, None),
        ("w4", "{points} 오페라에서 끝나게 {mode}", {"end_location": {"landmark": "오페라"}}, None),
        ("w5", "서울에서 시작해서 {points} 오페라로 마무리하게 {mode}", {"start_location": {"city": "Seoul"}, "end_location": {"landmark": "오페라"}}, None),
        ("w6", "저장된 일정 기준으로 {points} {mode}", {"trip_id": "trip-route-06"}, {"trip_id": "trip-route-06"}),
    ]

    cases: list[ParserCase] = []
    for point_spec, mode_spec, wrapper_spec in product(
        point_specs,
        mode_specs,
        wrapper_specs,
    ):
        point_name, point_text, point_expected = point_spec
        mode_name, mode_text, mode_expected = mode_spec
        wrapper_name, wrapper_template, wrapper_expected, wrapper_context = wrapper_spec
        message = wrapper_template.format(points=point_text, mode=mode_text)
        expected = _merge_dicts(
            {"clarify": {"needed": False}},
            point_expected,
            mode_expected,
            wrapper_expected,
        )
        cases.append(
            ParserCase(
                name=f"{point_name}_{mode_name}_{wrapper_name}",
                message=message,
                expected=expected,
                context=wrapper_context,
            )
        )
    return cases


def _recommend_venue_cases() -> list[ParserCase]:
    venue_specs = [
        ("v1", "파리에서 분위기 좋은 카페", {"venue_type": "cafe", "destination": {"city": "Paris"}}),
        ("v2", "파리 맛집", {"venue_type": "restaurant", "destination": {"city": "Paris"}}),
        ("v3", "파리 명소", {"venue_type": "attraction", "destination": {"city": "Paris"}}),
        ("v4", "파리 카페랑 맛집", {"venue_type": "mixed", "destination": {"city": "Paris"}}),
        ("v5", "파리 에펠탑 근처 카페", {"venue_type": "cafe", "destination": {"city": "Paris"}, "area": "near_eiffel_tower", "landmark": "eiffel_tower"}),
    ]
    count_specs = [
        ("c1", "3곳 추천해줘", {"count": 3}),
        ("c2", "5곳 추천해줘", {"count": 5}),
        ("c3", "7군데 알려줘", {"count": 7}),
        ("c4", "1개만 추천해줘", {"count": 1}),
        ("c5", "20곳 추천해줘", {"count": 20}),
    ]
    modifier_specs = [
        ("m1", "가성비로", {"budget": {"budget_mode": "save"}}),
        ("m2", "성인 2명 기준으로", {"party": {"adult": 2}}),
        ("m3", "가족여행이라 아이랑 가기 좋게", {"party": {"adult": 1, "elementary": 1, "trip_style": "family"}}),
        ("m4", "쇼핑하기 좋은 곳으로", {"themes": ["shopping"]}),
        ("m5", "야경 좋은 곳으로", {"themes": ["night_view"]}),
        ("m6", "루브르는 빼고 에펠탑은 꼭 포함해서", {"must_include": ["에펠탑"], "must_avoid": ["루브르"]}),
    ]

    cases: list[ParserCase] = []
    for venue_spec, count_spec, modifier_spec in product(
        venue_specs,
        count_specs,
        modifier_specs,
    ):
        venue_name, venue_text, venue_expected = venue_spec
        count_name, count_text, count_expected = count_spec
        modifier_name, modifier_text, modifier_expected = modifier_spec
        message = f"{venue_text} {modifier_text} {count_text}"
        expected = _merge_dicts(
            {"clarify": {"needed": False}},
            venue_expected,
            count_expected,
            modifier_expected,
        )
        cases.append(
            ParserCase(
                name=f"{venue_name}_{count_name}_{modifier_name}",
                message=message,
                expected=expected,
            )
        )
    return cases


def _manage_trip_cases() -> list[ParserCase]:
    cases: list[ParserCase] = []

    save_titles = [
        ("s1", "'파리 여름 여행'", "파리 여름 여행"),
        ("s2", "'파리 가족 여행'", "파리 가족 여행"),
        ("s3", "'파리 미식 여행'", "파리 미식 여행"),
        ("s4", "'파리 커플 여행'", "파리 커플 여행"),
        ("s5", "'파리 가을 여행'", "파리 가을 여행"),
    ]
    save_templates = [
        ("t1", "현재 일정을 {title}으로 저장해줘", {"trip_id": "trip-manage-current"}, {"trip_id": "trip-manage-current"}),
        ("t2", "이 일정 {title}으로 저장해줘", None, None),
        ("t3", "지금 만든 일정 {title}으로 보관해줘", None, None),
        ("t4", "이번 여행 일정 {title}으로 save 해줘", None, None),
        ("t5", "파리 일정 {title}으로 저장", None, None),
        ("t6", "플랜을 {title}으로 저장해줘", None, None),
    ]
    for title_spec, template_spec in product(save_titles, save_templates):
        title_name, quoted_title, title_value = title_spec
        template_name, template, extra_expected, context = template_spec
        message = template.format(title=quoted_title)
        expected = _merge_dicts(
            {"operation": "save", "trip_title": title_value, "clarify": {"needed": False}},
            extra_expected or {},
        )
        cases.append(ParserCase(name=f"save_{title_name}_{template_name}", message=message, expected=expected, context=context))

    list_refs = [
        ("l1", "저장한 일정", {"scope": "saved"}),
        ("l2", "내 일정", {"scope": "saved"}),
        ("l3", "모든 일정", {"scope": "all"}),
        ("l4", "전체 일정", {"scope": "all"}),
        ("l5", "최근 일정 목록", {"scope": "recent"}),
    ]
    list_templates = [
        ("t1", "{ref} 목록 보여줘"),
        ("t2", "{ref} 리스트 확인해줘"),
        ("t3", "{ref} 조회해줘"),
        ("t4", "{ref} 불러줘"),
        ("t5", "{ref} 정리해서 보여줘"),
        ("t6", "{ref} 뭐가 있는지 알려줘"),
    ]
    for ref_spec, template_spec in product(list_refs, list_templates):
        ref_name, ref_text, ref_expected = ref_spec
        template_name, template = template_spec
        message = template.format(ref=ref_text)
        expected = _merge_dicts({"operation": "list", "clarify": {"needed": False}}, ref_expected)
        cases.append(ParserCase(name=f"list_{ref_name}_{template_name}", message=message, expected=expected))

    retrieve_refs = [
        ("r1", "현재 일정", {"trip_id": "trip-manage-current", "scope": "current"}, {"trip_id": "trip-manage-current"}),
        ("r2", "trip-201 일정", {"trip_id": "trip-201", "scope": "current"}, None),
        ("r3", "trip-203 일정", {"trip_id": "trip-203", "scope": "current"}, None),
        ("r4", "trip-204 일정", {"trip_id": "trip-204", "scope": "current"}, None),
        ("r5", "trip-205 일정", {"trip_id": "trip-205", "scope": "current"}, None),
    ]
    retrieve_templates = [
        ("t1", "{ref} 보여줘"),
        ("t2", "{ref} 조회해줘"),
        ("t3", "{ref} 열어줘"),
        ("t4", "{ref} 확인하고 싶어"),
        ("t5", "{ref} 불러와줘"),
        ("t6", "{ref} 내용 보여줘"),
    ]
    for ref_spec, template_spec in product(retrieve_refs, retrieve_templates):
        ref_name, ref_text, ref_expected, context = ref_spec
        template_name, template = template_spec
        message = template.format(ref=ref_text)
        expected = _merge_dicts({"operation": "retrieve", "clarify": {"needed": False}}, ref_expected)
        cases.append(ParserCase(name=f"retrieve_{ref_name}_{template_name}", message=message, expected=expected, context=context))

    rename_refs = [
        ("n1", "trip-301 일정 제목을", "파리 가족 여행", {"trip_id": "trip-301"}),
        ("n2", "trip-302 일정 이름을", "파리 미식 여행", {"trip_id": "trip-302"}),
        ("n3", "현재 일정 제목을", "파리 야경 여행", {"trip_id": "trip-manage-rename"}),
        ("n4", "trip-303 일정 제목을", "파리 카페 여행", {"trip_id": "trip-303"}),
        ("n5", "현재 일정 이름을", "파리 겨울 여행", {"trip_id": "trip-manage-rename-2"}),
    ]
    rename_templates = [
        ("t1", "{ref} {title}으로 바꿔줘"),
        ("t2", "{ref} {title}으로 변경해줘"),
        ("t3", "{ref} {title}으로 수정해줘"),
        ("t4", "{ref} {title}으로 rename 해줘"),
        ("t5", "{ref} {title}로 바꿔"),
        ("t6", "{ref} {title}로 변경"),
    ]
    for ref_spec, template_spec in product(rename_refs, rename_templates):
        ref_name, ref_text, title_value, ref_expected = ref_spec
        template_name, template = template_spec
        context = None
        if ref_text.startswith("현재 일정"):
            context = {"trip_id": ref_expected["trip_id"]}
        message = template.format(ref=ref_text, title=title_value)
        expected = _merge_dicts(
            {
                "operation": "rename",
                "trip_title": title_value,
                "clarify": {"needed": False},
            },
            ref_expected,
        )
        cases.append(ParserCase(name=f"rename_{ref_name}_{template_name}", message=message, expected=expected, context=context))

    delete_refs = [
        ("d1", "현재 일정", {"trip_id": "trip-manage-delete", "scope": "current"}, {"trip_id": "trip-manage-delete"}),
        ("d2", "trip-401 일정", {"trip_id": "trip-401", "scope": "current"}, None),
        ("d3", "trip-402 일정", {"trip_id": "trip-402", "scope": "current"}, None),
        ("d4", "저장한 일정", {"scope": "saved"}, None),
        ("d5", "최근 일정", {"scope": "recent"}, None),
    ]
    delete_templates = [
        ("t1", "{ref} 삭제해줘"),
        ("t2", "{ref} 지워줘"),
        ("t3", "{ref} 없애줘"),
        ("t4", "{ref} 삭제"),
        ("t5", "{ref} 지워"),
        ("t6", "{ref} 제거해줘"),
    ]
    for ref_spec, template_spec in product(delete_refs, delete_templates):
        ref_name, ref_text, ref_expected, context = ref_spec
        template_name, template = template_spec
        message = template.format(ref=ref_text)
        expected = _merge_dicts({"operation": "delete", "clarify": {"needed": False}}, ref_expected)
        cases.append(ParserCase(name=f"delete_{ref_name}_{template_name}", message=message, expected=expected, context=context))

    return cases


def _user_profile_cases() -> list[ParserCase]:
    cases: list[ParserCase] = []
    pace_specs = [
        ("p1", "여유롭게 다니고", {"profile": {"pace_level": "slow"}}),
        ("p2", "빡세게 다니고", {"profile": {"pace_level": "fast"}}),
        ("p3", "적당히 다니고", {"profile": {"pace_level": "normal"}}),
        ("p4", "천천히 둘러보고", {"profile": {"pace_level": "slow"}}),
        ("p5", "넉넉하게 움직이고", {"profile": {"pace_level": "slow"}}),
    ]
    theme_specs = [
        ("t1", "카페랑 맛집 위주로", {"profile": {"preferred_themes": ["foodie", "cafe"]}}),
        ("t2", "쇼핑 위주로", {"profile": {"preferred_themes": ["shopping"]}}),
        ("t3", "야경 좋아하고", {"profile": {"preferred_themes": ["night_view"]}}),
        ("t4", "에펠탑 근처 선호하고", {"profile": {"preferred_areas": ["near_eiffel_tower"], "preferred_landmarks": ["eiffel_tower"]}}),
        ("t5", "미식이랑 카페 좋아하고", {"profile": {"preferred_themes": ["foodie", "cafe"]}}),
    ]
    extra_specs = [
        ("e1", "4성급 호텔 선호해", {"profile": {"accommodation_star_rating": 4}}),
        ("e2", "가성비 스타일이야", {"profile": {"budget_mode": "save"}}),
        ("e3", "대중교통 위주로 다녀", {"profile": {"travel_mode": "transit"}}),
        ("e4", "디저트랑 커피 좋아해", {"profile": {"food_preferences": ["dessert", "coffee"]}}),
    ]
    for pace_spec, theme_spec, extra_spec in product(
        pace_specs,
        theme_specs,
        extra_specs,
    ):
        pace_name, pace_text, pace_expected = pace_spec
        theme_name, theme_text, theme_expected = theme_spec
        extra_name, extra_text, extra_expected = extra_spec
        message = f"내 여행 프로필에 {pace_text} {theme_text} {extra_text} 저장해줘"
        expected = _merge_dicts(
            {"operation": "update", "clarify": {"needed": False}},
            pace_expected,
            theme_expected,
            extra_expected,
        )
        cases.append(ParserCase(name=f"update_{pace_name}_{theme_name}_{extra_name}", message=message, expected=expected))

    retrieve_phrases = [
        "내 여행 프로필 보여줘",
        "내 프로필 조회해줘",
        "선호사항 불러줘",
        "내 여행 취향 확인해줘",
        "여행 프로필 정보 보여줘",
    ]
    endings = [
        "지금",
        "한 번",
        "바로",
        "먼저",
        "상세히",
        "간단히",
        "요약해서",
        "정리해서",
        "다시",
        "부탁해",
    ]
    for index, (phrase, ending) in enumerate(product(retrieve_phrases, endings), start=1):
        message = f"{phrase} {ending}".strip()
        expected = {"operation": "retrieve", "clarify": {"needed": False}}
        cases.append(ParserCase(name=f"retrieve_{index:03d}", message=message, expected=expected))

    return cases


def _travel_style_cases() -> list[ParserCase]:
    pace_budget_specs = [
        ("pb1", "가성비로 여유롭게", {"pace_level": "slow", "budget_mode": "save"}),
        ("pb2", "럭셔리하게 천천히", {"pace_level": "slow", "budget_mode": "flex"}),
        ("pb3", "적당한 예산으로 적당히", {"pace_level": "normal", "budget_mode": "normal"}),
        ("pb4", "빡세게 다니고 아껴서", {"pace_level": "fast", "budget_mode": "save"}),
        ("pb5", "느긋하게 프리미엄으로", {"pace_level": "slow", "budget_mode": "flex"}),
    ]
    theme_specs = [
        ("th1", "카페랑 야경 좋아하고", {"style_tags": ["cafe", "night_view"], "venue_focus": ["cafe", "night_view"]}),
        ("th2", "맛집이랑 쇼핑 좋아하고", {"style_tags": ["foodie", "shopping"], "venue_focus": ["restaurant", "shopping"]}),
        ("th3", "미술관이랑 역사 좋아하고", {"style_tags": ["museum", "history"], "venue_focus": ["museum"]}),
        ("th4", "공원 산책 좋아하고", {"style_tags": ["nature"], "venue_focus": ["park"]}),
        ("th5", "명소랑 문화 공연 좋아하고", {"style_tags": ["culture"], "venue_focus": ["attraction"]}),
    ]
    mode_specs = [
        ("m1", "혼자 여행하는 편이야", {"trip_style": "solo"}),
        ("m2", "커플 여행 선호해", {"trip_style": "couple"}),
        ("m3", "친구랑 다니는 편이야", {"trip_style": "friends"}),
        ("m4", "가족여행 좋아해", {"trip_style": "family"}),
        ("m5", "대중교통 위주야", {"travel_mode": "transit"}),
        ("m6", "걸어다니는 편이야", {"travel_mode": "walk"}),
    ]

    cases: list[ParserCase] = []
    for pace_budget_spec, theme_spec, mode_spec in product(
        pace_budget_specs,
        theme_specs,
        mode_specs,
    ):
        pace_budget_name, pace_budget_text, pace_budget_expected = pace_budget_spec
        theme_name, theme_text, theme_expected = theme_spec
        mode_name, mode_text, mode_expected = mode_spec
        message = f"내 여행 스타일 분석해줘. {pace_budget_text} {theme_text} {mode_text}"
        expected = _merge_dicts(
            {"clarify": {"needed": False}},
            pace_budget_expected,
            theme_expected,
            mode_expected,
        )
        cases.append(
            ParserCase(
                name=f"{pace_budget_name}_{theme_name}_{mode_name}",
                message=message,
                expected=expected,
            )
        )
    return cases


def _trip_diary_cases() -> list[ParserCase]:
    scope_specs = [
        ("s1", "2일차 여행 일기", {"target_day": 2}, None),
        ("s2", "2026년 7월 10일 여행 일기", {"entry_date": "2026-07-10"}, None),
        ("s3", "여행 일기", {"trip_id": "trip-diary-03"}, {"trip_id": "trip-diary-03"}),
        ("s4", "루브르랑 에펠탑 여행 일기", {"highlights": ["루브르", "에펠탑"]}, None),
        ("s5", "셋째날 여행 일기", {"target_day": 3}, None),
    ]
    style_specs = [
        ("st1", "감성적으로 써줘", {"tone": "emotional", "format": "paragraph"}),
        ("st2", "블로그 스타일로 써줘", {"tone": "blog", "format": "paragraph"}),
        ("st3", "정보 정리해서 써줘", {"tone": "informative", "format": "paragraph"}),
        ("st4", "리스트로 써줘", {"tone": "casual", "format": "bullet"}),
        ("st5", "타임라인으로 써줘", {"tone": "casual", "format": "timeline"}),
    ]
    detail_specs = [
        ("dt1", "메모: 노을이 예뻤어", {"notes": "노을이 예뻤어"}),
        ("dt2", "날씨도 넣어줘", {"include_weather": True}),
        ("dt3", "비용도 정리해줘", {"include_cost": True}),
        ("dt4", "루브르랑 오르세 포함해서", {"highlights": ["루브르", "오르세"]}),
        ("dt5", "날씨랑 비용도 넣고 메모: 카페가 좋았어", {"include_weather": True, "include_cost": True, "notes": "카페가 좋았어"}),
        ("dt6", "포인트: 가족 모두 만족했어", {"notes": "가족 모두 만족했어"}),
    ]

    cases: list[ParserCase] = []
    for scope_spec, style_spec, detail_spec in product(
        scope_specs,
        style_specs,
        detail_specs,
    ):
        scope_name, scope_text, scope_expected, scope_context = scope_spec
        style_name, style_text, style_expected = style_spec
        detail_name, detail_text, detail_expected = detail_spec
        message = f"{scope_text} {style_text}. {detail_text}"
        expected = _merge_dicts(
            {"clarify": {"needed": False}},
            scope_expected,
            style_expected,
            detail_expected,
        )
        cases.append(
            ParserCase(
                name=f"{scope_name}_{style_name}_{detail_name}",
                message=message,
                expected=expected,
                context=scope_context,
            )
        )
    return cases


class ParserTddMatrixTests(unittest.TestCase):
    maxDiff = None

    def _run_cases(self, cases: list[ParserCase], parser_fn) -> None:
        self.assertEqual(len(cases), 150)
        for case in cases:
            with self.subTest(case=case.name):
                payload = parser_fn(case.message, case.context).model_dump()
                _assert_subset(self, payload, case.expected)

    def test_shared_context_parser_tdd_matrix(self) -> None:
        self._run_cases(_shared_context_cases(), parse_shared_context)

    def test_request_bundle_parser_tdd_matrix(self) -> None:
        self._run_cases(_request_bundle_cases(), parse_request_bundle)

    def test_create_plan_parser_tdd_matrix(self) -> None:
        cases = _create_plan_cases()
        self.assertEqual(len(cases), 150)
        with patch("parser_api.parsers.create_plan.parser._call_llm_structured", return_value={}):
            for case in cases:
                with self.subTest(case=case.name):
                    payload = parse_create_plan(case.message, case.context).model_dump()
                    _assert_subset(self, payload, case.expected)

    def test_modify_plan_parser_tdd_matrix(self) -> None:
        cases = _modify_plan_cases()
        self.assertEqual(len(cases), 150)
        with patch("parser_api.parsers.modify_plan.parser._call_llm_structured", return_value={}):
            for case in cases:
                with self.subTest(case=case.name):
                    payload = parse_modify_plan(case.message, case.context).model_dump()
                    _assert_subset(self, payload, case.expected)

    def test_flight_search_parser_tdd_matrix(self) -> None:
        self._run_cases(_flight_search_cases(), parse_flight_search)

    def test_hotel_search_parser_tdd_matrix(self) -> None:
        self._run_cases(_hotel_search_cases(), parse_hotel_search)

    def test_estimate_budget_parser_tdd_matrix(self) -> None:
        self._run_cases(_estimate_budget_cases(), parse_estimate_budget)

    def test_flight_book_parser_tdd_matrix(self) -> None:
        self._run_cases(_flight_book_cases(), parse_flight_book)

    def test_hotel_book_parser_tdd_matrix(self) -> None:
        self._run_cases(_hotel_book_cases(), parse_hotel_book)

    def test_manage_booking_parser_tdd_matrix(self) -> None:
        self._run_cases(_manage_booking_cases(), parse_manage_booking)

    def test_optimize_route_parser_tdd_matrix(self) -> None:
        self._run_cases(_optimize_route_cases(), parse_optimize_route)

    def test_recommend_venue_parser_tdd_matrix(self) -> None:
        self._run_cases(_recommend_venue_cases(), parse_recommend_venue)

    def test_manage_trip_parser_tdd_matrix(self) -> None:
        self._run_cases(_manage_trip_cases(), parse_manage_trip)

    def test_user_profile_parser_tdd_matrix(self) -> None:
        self._run_cases(_user_profile_cases(), parse_user_profile)

    def test_travel_style_parser_tdd_matrix(self) -> None:
        self._run_cases(_travel_style_cases(), parse_travel_style)

    def test_trip_diary_parser_tdd_matrix(self) -> None:
        self._run_cases(_trip_diary_cases(), parse_trip_diary)
