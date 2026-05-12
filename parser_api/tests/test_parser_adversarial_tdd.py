from __future__ import annotations

import unittest
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


class ParserAdversarialTDDTests(unittest.TestCase):
    def test_shared_context_supports_slash_dates_and_couple_signal(self) -> None:
        payload = parse_shared_context("2026/07/10 인천에서 파리 가는 부부 여행")
        _assert_subset(
            self,
            payload.model_dump(),
            {
                "dates": {"start_date": "2026-07-10"},
                "party": {"adult": 2, "trip_style": "couple"},
            },
        )

    def test_request_bundle_detects_english_route_and_venue_terms(self) -> None:
        payload = parse_request_bundle("파리에서 shopping 하기 좋은 cafe 추천해주고 route optimize 해줘")
        _assert_subset(
            self,
            payload.model_dump(),
            {
                "actions": [
                    {"intent": "RECOMMEND_VENUE", "order": 1},
                    {"intent": "OPTIMIZE_ROUTE", "order": 2},
                ]
            },
        )

    def test_create_plan_handles_slash_dates_and_couple_trip(self) -> None:
        with patch("parser_api.parsers.create_plan.parser._call_llm_structured", return_value={}):
            payload = parse_create_plan("부부가 2026/07/10부터 3박4일 파리 여행 일정 짜줘")

        _assert_subset(
            self,
            payload.model_dump(),
            {
                "dates": {"start_date": "2026-07-10", "days": 4},
                "party": {"adult": 2, "trip_style": "couple"},
            },
        )

    def test_modify_plan_understands_english_day_marker(self) -> None:
        with patch("parser_api.parsers.modify_plan.parser._call_llm_structured", return_value={}):
            payload = parse_modify_plan("day 2에는 루브르 말고 오르세 넣어줘", {"trip_id": "trip-x"})

        _assert_subset(
            self,
            payload.model_dump(),
            {
                "operations": [
                    {
                        "target_day": 2,
                        "constraints_patch": {
                            "from_place": "루브르",
                            "to_place": "오르세",
                        },
                    }
                ]
            },
        )

    def test_flight_search_supports_slash_dates(self) -> None:
        payload = parse_flight_search("2026/07/10 인천에서 파리 가는 business 항공권 1000eur 이하로 찾아줘")
        _assert_subset(
            self,
            payload.model_dump(),
            {
                "departure_date": "2026-07-10",
                "cabin_class": "business",
                "max_price": 1000,
                "currency": "EUR",
            },
        )

    def test_flight_book_extracts_offer_ref_without_colon(self) -> None:
        payload = parse_flight_book("7월 10일 인천에서 파리 가는 항공권 offer FLT123 예약해줘")
        _assert_subset(
            self,
            payload.model_dump(),
            {
                "offer_ref": "FLT123",
                "clarify": {"needed": False},
            },
        )

    def test_hotel_search_supports_slash_ranges_and_eur_price(self) -> None:
        payload = parse_hotel_search("7/10부터 7/14까지 파리 에펠탑 근처 4-star 호텔 200eur 이하로 찾아줘")
        _assert_subset(
            self,
            payload.model_dump(),
            {
                "check_in_date": "2026-07-10",
                "check_out_date": "2026-07-14",
                "nights": 4,
                "area": "near_eiffel_tower",
                "max_price_per_night": 200,
                "currency": "EUR",
            },
        )

    def test_hotel_book_extracts_property_ref_without_colon(self) -> None:
        payload = parse_hotel_book("7월 10일 파리 호텔 예약해줘 property HTL555")
        _assert_subset(
            self,
            payload.model_dump(),
            {
                "property_ref": "HTL555",
                "clarify": {"needed": False},
            },
        )

    def test_estimate_budget_understands_english_component_token(self) -> None:
        payload = parse_estimate_budget("파리 3박4일 예산 계산해줘 food 빼고 다 포함해줘")
        _assert_subset(
            self,
            payload.model_dump(),
            {
                "components": {
                    "flight": True,
                    "hotel": True,
                    "food": False,
                    "transport": True,
                }
            },
        )

    def test_manage_booking_extracts_booking_id_without_prefix_leak(self) -> None:
        payload = parse_manage_booking("booking id BK123 상태 확인해줘")
        _assert_subset(
            self,
            payload.model_dump(),
            {
                "booking_id": "BK123",
                "operation": "retrieve",
            },
        )

    def test_manage_booking_only_sets_guest_change_when_explicit(self) -> None:
        payload = parse_manage_booking("예약번호 BK123 날짜만 7월 12일로 변경해줘")
        _assert_subset(
            self,
            payload.model_dump(),
            {
                "change_request": {
                    "check_in_date": "2026-07-12",
                    "departure_date": "2026-07-12",
                    "guests": None,
                }
            },
        )

    def test_manage_trip_supports_english_rename(self) -> None:
        payload = parse_manage_trip("rename trip-abc to Paris Family Trip")
        _assert_subset(
            self,
            payload.model_dump(),
            {
                "operation": "rename",
                "trip_id": "trip-abc",
                "trip_title": "Paris Family Trip",
            },
        )

    def test_manage_trip_supports_english_saved_list(self) -> None:
        payload = parse_manage_trip("show my saved trips")
        _assert_subset(
            self,
            payload.model_dump(),
            {
                "operation": "list",
                "scope": "saved",
            },
        )

    def test_optimize_route_understands_english_day_marker(self) -> None:
        payload = parse_optimize_route("day 2 에펠탑 오르세 route optimize 해줘")
        _assert_subset(
            self,
            payload.model_dump(),
            {
                "target_day": 2,
                "route_points": [{"name": "오르세"}, {"name": "에펠탑"}],
            },
        )

    def test_recommend_venue_understands_english_theme_and_venue_words(self) -> None:
        payload = parse_recommend_venue("파리에서 shopping 하기 좋은 cafe 2곳 추천해줘")
        _assert_subset(
            self,
            payload.model_dump(),
            {
                "venue_type": "cafe",
                "themes": ["shopping"],
                "count": 2,
            },
        )

    def test_user_profile_extracts_couple_and_long_walk_avoidance(self) -> None:
        payload = parse_user_profile("부부 여행이고 쇼핑이랑 미술관 좋아하고 많이 걷는 건 싫어")
        _assert_subset(
            self,
            payload.model_dump(),
            {
                "profile": {
                    "trip_style": "couple",
                    "preferred_themes": ["shopping", "museum"],
                    "avoid_preferences": ["long_walk"],
                }
            },
        )

    def test_travel_style_extracts_couple_and_long_walk_signal(self) -> None:
        payload = parse_travel_style("부부 여행이고 쇼핑이랑 미술관 좋아하고 많이 걷는 건 싫어")
        _assert_subset(
            self,
            payload.model_dump(),
            {
                "style_tags": ["shopping", "museum", "couple"],
                "trip_style": "couple",
            },
        )

    def test_trip_diary_supports_english_blog_and_note_marker(self) -> None:
        payload = parse_trip_diary("2일차 여행일기 blog 스타일로 note: 루브르 야경 중심으로 써줘")
        _assert_subset(
            self,
            payload.model_dump(),
            {
                "target_day": 2,
                "tone": "blog",
                "notes": "루브르 야경 중심으로 써줘",
            },
        )


if __name__ == "__main__":
    unittest.main()
