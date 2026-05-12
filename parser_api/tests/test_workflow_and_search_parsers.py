import unittest

from parser_api.parsers.classifier import extract_intent
from parser_api.parsers.estimate_budget.parser import parse_estimate_budget
from parser_api.parsers.flight_search.parser import parse_flight_search
from parser_api.parsers.hotel_search.parser import parse_hotel_search
from parser_api.parsers.workflow.request_bundle.parser import parse_request_bundle
from parser_api.parsers.workflow.shared_context.parser import parse_shared_context
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


class WorkflowAndSearchParserTests(unittest.TestCase):
    def test_shared_context_extracts_route_date_and_budget(self) -> None:
        payload = parse_shared_context(
            "7월 10일 인천에서 파리 가는 항공권 찾아줘. 예산은 300만원이야."
        ).model_dump()

        _assert_subset(
            self,
            payload,
            {
                "origin": {"city": "Incheon", "airport_code": "ICN"},
                "destination": {"city": "Paris", "country": "FR"},
                "dates": {"start_date": "2026-07-10", "source": "explicit"},
                "budget": {"budget_total": 3000000, "currency": "KRW"},
            },
        )

    def test_request_bundle_splits_flight_and_hotel_actions(self) -> None:
        payload = parse_request_bundle(
            "7월 10일 인천에서 파리 가는 왕복 항공권이랑 에펠탑 근처 4성급 호텔 예약해줘"
        ).model_dump()

        _assert_subset(
            self,
            payload,
            {
                "actions": [
                    {"intent": "FLIGHT_BOOK", "order": 1},
                    {"intent": "HOTEL_BOOK", "order": 2},
                ],
                "shared_context": {
                    "destination": {"city": "Paris"},
                    "dates": {"start_date": "2026-07-10"},
                },
            },
        )

    def test_request_bundle_splits_plan_and_budget_actions(self) -> None:
        payload = parse_request_bundle("파리 3박4일 일정 짜고 예산도 계산해줘").model_dump()

        _assert_subset(
            self,
            payload,
            {
                "actions": [
                    {"intent": "CREATE_PLAN", "order": 1},
                    {"intent": "ESTIMATE_BUDGET", "order": 2},
                ]
            },
        )

    def test_request_bundle_adds_dependency_for_create_then_modify(self) -> None:
        payload = parse_request_bundle(
            "파리 3박4일 일정 짜주고 1일차 오후에 루브르 대신 오르세로 바꿔줘"
        ).model_dump()

        _assert_subset(
            self,
            payload,
            {
                "actions": [
                    {"intent": "CREATE_PLAN", "order": 1},
                    {
                        "intent": "MODIFY_PLAN",
                        "order": 2,
                        "depends_on": ["step_1_create_plan"],
                    },
                ]
            },
        )

    def test_flight_search_parser_builds_payload(self) -> None:
        payload = parse_flight_search(
            "7월 10일 인천에서 파리 가는 왕복 직항 항공권 찾아줘. 비즈니스석으로."
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
                "clarify": {"needed": False},
            },
        )

    def test_hotel_search_parser_builds_payload(self) -> None:
        payload = parse_hotel_search(
            "7월 10일 체크인해서 에펠탑 근처 4성급 호텔 찾아줘. 성인 2명 방 2개."
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
            },
        )

    def test_estimate_budget_parser_builds_component_payload(self) -> None:
        payload = parse_estimate_budget(
            "파리 4박5일 여행 예산 계산해줘. 항공권, 호텔, 식비만 포함하고 4성급 기준으로."
        ).model_dump()

        _assert_subset(
            self,
            payload,
            {
                "destination": {"city": "Paris"},
                "dates": {"days": 5},
                "components": {
                    "flight": True,
                    "hotel": True,
                    "food": True,
                    "transport": False,
                    "activities": False,
                    "shopping": False,
                },
                "hotel_star_rating": 4,
                "clarify": {"needed": False},
            },
        )

    def test_classifier_returns_request_bundle_for_multi_action_message(self) -> None:
        intent = extract_intent(
            "파리 3박4일 일정 짜주고 항공권이랑 호텔도 찾아줘"
        )
        self.assertEqual(intent.value, "REQUEST_BUNDLE")

    def test_classifier_returns_request_bundle_for_create_then_modify_message(self) -> None:
        intent = extract_intent(
            "파리 3박4일 일정 짜주고 1일차 오후에 루브르 대신 오르세로 바꿔줘"
        )
        self.assertEqual(intent.value, "REQUEST_BUNDLE")

    def test_run_agent_returns_bundle_payload(self) -> None:
        response = run_agent(
            AgentRunRequest(
                message="파리 3박4일 일정 짜주고 예산도 계산해줘",
                context={},
            )
        )

        self.assertEqual(response.status, "DONE")
        self.assertEqual(response.intent, "REQUEST_BUNDLE")
        self.assertIn("bundle", response.data)
