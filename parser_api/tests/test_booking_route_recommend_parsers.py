import unittest

from parser_api.parsers.classifier import extract_intent
from parser_api.parsers.flight_book.parser import parse_flight_book
from parser_api.parsers.hotel_book.parser import parse_hotel_book
from parser_api.parsers.manage_booking.parser import parse_manage_booking
from parser_api.parsers.optimize_route.parser import parse_optimize_route
from parser_api.parsers.recommend_venue.parser import parse_recommend_venue
from parser_api.parsers.workflow.request_bundle.parser import parse_request_bundle
from parser_api.schemas import AgentRunRequest
from parser_api.services.agent_service import run_agent


def _assert_subset(test_case: unittest.TestCase, actual, expected) -> None:
    if isinstance(expected, dict):
        test_case.assertIsInstance(actual, dict)
        for key, value in expected.items():
            test_case.assertIn(key, actual)
            _assert_subset(test_case, actual[key], value)
        return

    if isinstance(expected, list):
        test_case.assertEqual(len(actual), len(expected))
        for actual_item, expected_item in zip(actual, expected):
            _assert_subset(test_case, actual_item, expected_item)
        return

    test_case.assertEqual(actual, expected)


class BookingRouteRecommendParserTests(unittest.TestCase):
    def test_flight_book_parser_builds_payload(self) -> None:
        payload = parse_flight_book(
            "7월 10일 인천에서 파리 가는 왕복 직항 항공권 예약해줘. 비즈니스석으로.",
            context={"offer_ref": "flt_offer_123"},
        ).model_dump()

        _assert_subset(
            self,
            payload,
            {
                "origin": {"airport_code": "ICN"},
                "destination": {"city": "Paris"},
                "departure_date": "2026-07-10",
                "trip_type": "round_trip",
                "direct_only": True,
                "cabin_class": "business",
                "offer_ref": "flt_offer_123",
                "clarify": {"needed": False},
            },
        )

    def test_hotel_book_parser_builds_payload(self) -> None:
        payload = parse_hotel_book(
            "7월 10일 체크인해서 에펠탑 근처 4성급 호텔 예약해줘. 성인 2명 방 2개.",
            context={"property_ref": "hotel_prop_77"},
        ).model_dump()

        _assert_subset(
            self,
            payload,
            {
                "destination": {"city": "Paris"},
                "area": "near_eiffel_tower",
                "landmark": "eiffel_tower",
                "check_in_date": "2026-07-10",
                "star_rating": 4,
                "guests": 2,
                "rooms": 2,
                "property_ref": "hotel_prop_77",
                "clarify": {"needed": False},
            },
        )

    def test_manage_booking_parser_builds_modify_request(self) -> None:
        payload = parse_manage_booking(
            "호텔 예약 날짜를 7월 12일부터 7월 15일까지로 변경해줘",
            context={"booking_id": "bk_123"},
        ).model_dump()

        _assert_subset(
            self,
            payload,
            {
                "operation": "modify",
                "booking_domain": "hotel",
                "booking_id": "bk_123",
                "change_request": {
                    "check_in_date": "2026-07-12",
                    "check_out_date": "2026-07-15",
                },
                "clarify": {"needed": False},
            },
        )

    def test_manage_booking_cancel_requires_confirmation(self) -> None:
        payload = parse_manage_booking(
            "항공권 예약 취소해줘",
            context={"booking_id": "flight_bk_99"},
        ).model_dump()

        _assert_subset(
            self,
            payload,
            {
                "operation": "cancel",
                "booking_domain": "flight",
                "booking_id": "flight_bk_99",
                "requires_confirmation": True,
                "clarify": {"needed": False},
            },
        )

    def test_optimize_route_parser_builds_payload(self) -> None:
        payload = parse_optimize_route(
            "루브르, 오르세, 에펠탑 동선 최적화해줘. 대중교통 위주로."
        ).model_dump()

        _assert_subset(
            self,
            payload,
            {
                "route_points": [
                    {"name": "루브르"},
                    {"name": "오르세"},
                    {"name": "에펠탑"},
                ],
                "travel_mode": "transit",
                "optimize": "min_time",
                "clarify": {"needed": False},
            },
        )

    def test_recommend_venue_parser_builds_payload(self) -> None:
        payload = parse_recommend_venue(
            "파리에서 분위기 좋은 카페 5곳 추천해줘"
        ).model_dump()

        _assert_subset(
            self,
            payload,
            {
                "venue_type": "cafe",
                "destination": {"city": "Paris"},
                "count": 5,
                "clarify": {"needed": False},
            },
        )

    def test_classifier_prefers_manage_booking_over_cancel_plan(self) -> None:
        intent = extract_intent(
            "호텔 예약 취소해줘",
            context={"booking_id": "hotel_bk_1"},
        )
        self.assertEqual(intent.value, "MANAGE_BOOKING")

    def test_request_bundle_splits_flight_and_hotel_book_actions(self) -> None:
        payload = parse_request_bundle(
            "7월 10일 인천에서 파리 가는 항공권 예약하고 에펠탑 근처 호텔도 예약해줘"
        ).model_dump()

        _assert_subset(
            self,
            payload,
            {
                "actions": [
                    {"intent": "FLIGHT_BOOK", "order": 1},
                    {"intent": "HOTEL_BOOK", "order": 2},
                ]
            },
        )

    def test_run_agent_returns_route_optimization_payload(self) -> None:
        response = run_agent(
            AgentRunRequest(
                message="루브르, 오르세, 에펠탑 동선 최적화해줘",
                context={},
            )
        )

        self.assertEqual(response.status, "DONE")
        self.assertEqual(response.intent, "OPTIMIZE_ROUTE")
        self.assertIn("route_optimization", response.data)

