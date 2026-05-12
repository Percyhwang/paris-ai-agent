from __future__ import annotations

import unittest
from contextlib import ExitStack
from unittest.mock import patch

try:
    from parser_api.executors.fastmcp import FastMcpExecutor
except ModuleNotFoundError:
    FastMcpExecutor = None

from parser_api.executors.localmcp import LocalMcpExecutor
from parser_api.schemas import AgentRunRequest
from parser_api.services.agent_service import run_agent
from parser_api.services.profile_store import reset_user_profile
from parser_api.services.trip_store import TRIP_STATE, reset_trip_store
from parser_api.executors.registry import build_default_executor_registry
from parser_api.executors.stub import StubIntentExecutor
from parser_api.intents import Intent


def _assert_subset(test_case: unittest.TestCase, actual, expected) -> None:
    if isinstance(expected, dict):
        test_case.assertIsInstance(actual, dict)
        for key, value in expected.items():
            test_case.assertIn(key, actual)
            _assert_subset(test_case, actual[key], value)
        return

    if isinstance(expected, list):
        test_case.assertIsInstance(actual, list)
        test_case.assertGreaterEqual(len(actual), len(expected))
        for actual_item, expected_item in zip(actual, expected):
            _assert_subset(test_case, actual_item, expected_item)
        return

    test_case.assertEqual(actual, expected)


class OrchestrationIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_trip_store()
        reset_user_profile()
        self._patches = ExitStack()
        self._patches.enter_context(
            patch("parser_api.parsers.create_plan.parser._call_llm_structured", return_value={})
        )
        self._patches.enter_context(
            patch("parser_api.parsers.modify_plan.parser._call_llm_structured", return_value={})
        )

    def tearDown(self) -> None:
        self._patches.close()
        reset_trip_store()
        reset_user_profile()

    def test_run_agent_direct_integration_matrix(self) -> None:
        cases = [
            {
                "name": "create_plan_done",
                "message": "파리 7월 10일부터 7월 13일까지 일정 짜줘",
                "context": {},
                "expected": {
                    "status": "DONE",
                    "intent": "CREATE_PLAN",
                    "clarify": {"needed": False},
                    "data": {
                        "plan": {
                            "dates": {
                                "start_date": "2026-07-10",
                                "end_date": "2026-07-13",
                                "days": 4,
                            }
                        }
                    },
                },
            },
            {
                "name": "flight_search_done",
                "message": "7월 10일 인천에서 파리 가는 왕복 직항 항공권 찾아줘",
                "context": {},
                "expected": {
                    "status": "DONE",
                    "intent": "FLIGHT_SEARCH",
                    "clarify": {"needed": False},
                    "data": {
                        "flight_search": {
                            "origin": {"airport_code": "ICN"},
                            "destination": {"city": "Paris"},
                            "departure_date": "2026-07-10",
                            "direct_only": True,
                        }
                    },
                },
            },
            {
                "name": "hotel_search_ask",
                "message": "에펠탑 근처 4성급 호텔 찾아줘",
                "context": {},
                "expected": {
                    "status": "ASK",
                    "intent": "HOTEL_SEARCH",
                    "clarify": {"needed": True, "missing_fields": ["check_in_date"]},
                    "data": {
                        "hotel_search": {
                            "area": "near_eiffel_tower",
                            "landmark": "eiffel_tower",
                            "star_rating": 4,
                        }
                    },
                },
            },
            {
                "name": "flight_book_confirmation",
                "message": "7월 10일 인천에서 파리 가는 항공권 offer FLT123 예약해줘",
                "context": {},
                "expected": {
                    "status": "ASK",
                    "intent": "FLIGHT_BOOK",
                    "clarify": {"needed": False},
                    "data": {
                        "flight_book": {
                            "departure_date": "2026-07-10",
                            "offer_ref": "FLT123",
                        },
                        "confirmation": {
                            "needed": True,
                            "intent": "FLIGHT_BOOK",
                        },
                    },
                },
            },
            {
                "name": "hotel_book_confirmation",
                "message": "7월 10일 체크인 파리 에펠탑 근처 호텔 property HTL555 예약해줘",
                "context": {},
                "expected": {
                    "status": "ASK",
                    "intent": "HOTEL_BOOK",
                    "clarify": {"needed": False},
                    "data": {
                        "hotel_book": {
                            "check_in_date": "2026-07-10",
                            "property_ref": "HTL555",
                        },
                        "confirmation": {
                            "needed": True,
                            "intent": "HOTEL_BOOK",
                        },
                    },
                },
            },
            {
                "name": "manage_booking_cancel_confirmation",
                "message": "booking id BK123 호텔 예약 취소해줘",
                "context": {},
                "expected": {
                    "status": "ASK",
                    "intent": "MANAGE_BOOKING",
                    "clarify": {"needed": False},
                    "data": {
                        "manage_booking": {
                            "operation": "cancel",
                            "booking_domain": "hotel",
                            "booking_id": "BK123",
                        },
                        "confirmation": {
                            "needed": True,
                            "intent": "MANAGE_BOOKING",
                        },
                    },
                },
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                response = run_agent(
                    AgentRunRequest(
                        message=case["message"],
                        context=case["context"],
                    )
                ).model_dump()
                _assert_subset(self, response, case["expected"])

    def test_run_agent_create_plan_persists_trip_state(self) -> None:
        response = run_agent(
            AgentRunRequest(
                message="파리 7월 10일부터 7월 13일까지 일정 짜줘",
                context={},
            )
        )

        self.assertEqual(response.status, "DONE")
        self.assertTrue(response.trip_id)
        self.assertIn(response.trip_id, TRIP_STATE)
        _assert_subset(
            self,
            TRIP_STATE[response.trip_id],
            {
                "intent": "CREATE_PLAN",
                "plan": {
                    "dates": {
                        "start_date": "2026-07-10",
                        "end_date": "2026-07-13",
                        "days": 4,
                    }
                },
                "meta": {
                    "mcp": "fastmcp",
                    "server": "planning-service",
                    "tool": "create_plan",
                },
            },
        )
        self.assertTrue(TRIP_STATE[response.trip_id]["itinerary_days"])
        first_item = TRIP_STATE[response.trip_id]["itinerary_days"][0]["items"][0]
        self.assertNotEqual(first_item["title"], "파리 산책")
        self.assertTrue(first_item["place"]["coordinates"])
        self.assertIn("데이터 기반", TRIP_STATE[response.trip_id]["route_summary"])

    def test_run_agent_recommend_venue_returns_catalog_recommendations(self) -> None:
        response = run_agent(
            AgentRunRequest(
                message="파리에서 분위기 좋은 카페 5곳 추천해줘",
                context={},
            )
        )

        self.assertEqual(response.status, "DONE")
        recommendations = response.data["venue_recommendation"]["recommendations"]
        self.assertEqual(len(recommendations), 5)
        self.assertFalse(any("Spot" in recommendation["name"] for recommendation in recommendations))
        self.assertTrue(all(recommendation["coordinates"] for recommendation in recommendations))
        self.assertTrue(all(recommendation["area"] for recommendation in recommendations))

    def test_run_agent_optimize_route_returns_resolved_places(self) -> None:
        response = run_agent(
            AgentRunRequest(
                message="루브르, 오르세, 에펠탑 동선 최적화해줘. 대중교통 위주로.",
                context={},
            )
        )

        self.assertEqual(response.status, "DONE")
        optimization = response.data["route_optimization"]
        self.assertEqual(len(optimization["ordered_points"]), 3)
        self.assertEqual(len(optimization["resolved_places"]), 3)
        self.assertGreater(optimization["estimated_distance_km"], 0)
        self.assertIn("재정렬", optimization["route_summary"])

    def test_run_agent_memorable_transit_trip_prefers_curated_places(self) -> None:
        response = run_agent(
            AgentRunRequest(
                message="7월3일부터 11일까지 친구들이랑 파리러로 여행을 가는데 대중교통을 이용할거야 기억에 남는 파리 여행 계획 만들어줘",
                context={},
            )
        )

        self.assertEqual(response.status, "DONE")
        plan = response.data["plan"]
        self.assertEqual(plan["mobility"]["travel_mode"], "transit")
        self.assertEqual(plan["party"]["adult"], 3)
        self.assertIn("landmark", plan["preferences"]["themes"])
        first_day_items = response.data["itinerary_days"][0]["items"]
        self.assertTrue(all(item["place"]["place_id"] for item in first_day_items))
        self.assertTrue(all(not str(item["place"]["place_id"]).startswith("osm-") for item in first_day_items))

    def test_default_executor_registry_keeps_search_and_booking_on_stub_scope(self) -> None:
        registry = build_default_executor_registry()

        primary_expectations = {
            Intent.CREATE_PLAN: LocalMcpExecutor if FastMcpExecutor is None else FastMcpExecutor,
            Intent.MODIFY_PLAN: LocalMcpExecutor if FastMcpExecutor is None else FastMcpExecutor,
            Intent.ESTIMATE_BUDGET: LocalMcpExecutor if FastMcpExecutor is None else FastMcpExecutor,
            Intent.OPTIMIZE_ROUTE: LocalMcpExecutor if FastMcpExecutor is None else FastMcpExecutor,
            Intent.RECOMMEND_VENUE: LocalMcpExecutor if FastMcpExecutor is None else FastMcpExecutor,
            Intent.MANAGE_TRIP: LocalMcpExecutor if FastMcpExecutor is None else FastMcpExecutor,
            Intent.USER_PROFILE: LocalMcpExecutor if FastMcpExecutor is None else FastMcpExecutor,
            Intent.TRAVEL_STYLE: LocalMcpExecutor if FastMcpExecutor is None else FastMcpExecutor,
            Intent.TRIP_DIARY: LocalMcpExecutor if FastMcpExecutor is None else FastMcpExecutor,
        }

        for intent, expected_type in primary_expectations.items():
            with self.subTest(intent=intent.value):
                self.assertIsInstance(registry.get(intent), expected_type)

        for intent in (
            Intent.FLIGHT_SEARCH,
            Intent.HOTEL_SEARCH,
            Intent.FLIGHT_BOOK,
            Intent.HOTEL_BOOK,
            Intent.MANAGE_BOOKING,
        ):
            with self.subTest(intent=intent.value):
                self.assertIsInstance(registry.get(intent), StubIntentExecutor)

    def test_run_agent_bundle_create_and_budget_finishes_done(self) -> None:
        response = run_agent(
            AgentRunRequest(
                message="파리 7월 10일부터 7월 13일까지 일정 짜주고 예산도 계산해줘",
                context={},
            )
        ).model_dump()

        self.assertEqual(response["status"], "DONE")
        self.assertNotIn("clarify", response["data"]["bundle"]["shared_context"])
        _assert_subset(
            self,
            response,
            {
                "intent": "REQUEST_BUNDLE",
                "clarify": {"needed": False},
                "data": {
                    "bundle": {
                        "meta": {"status_counts": {"DONE": 2}},
                        "results": [
                            {
                                "action_ref": "step_1_create_plan",
                                "status": "DONE",
                            },
                            {
                                "action_ref": "step_2_estimate_budget",
                                "status": "DONE",
                            },
                        ],
                    }
                },
            },
        )
        self.assertIn(response["trip_id"], TRIP_STATE)

    def test_run_agent_bundle_create_and_modify_propagates_trip_id(self) -> None:
        response = run_agent(
            AgentRunRequest(
                message="파리 7월 10일부터 7월 13일까지 일정 짜주고 2일차 오후 루브르 대신 오르세로 바꿔줘",
                context={},
            )
        ).model_dump()

        self.assertEqual(response["status"], "DONE")
        self.assertNotIn("clarify", response["data"]["bundle"]["shared_context"])
        _assert_subset(
            self,
            response,
            {
                "intent": "REQUEST_BUNDLE",
                "data": {
                    "bundle": {
                        "meta": {"status_counts": {"DONE": 2}},
                        "results": [
                            {
                                "action_ref": "step_1_create_plan",
                                "status": "DONE",
                            },
                            {
                                "action_ref": "step_2_modify_plan",
                                "status": "DONE",
                                "depends_on": ["step_1_create_plan"],
                                "trip_id": response["trip_id"],
                                "data": {
                                    "modify": {
                                        "trip_id": response["trip_id"],
                                        "operations": [
                                            {
                                                "target_day": 2,
                                                "target_slot": "afternoon",
                                                "constraints_patch": {
                                                    "from_place": "루브르",
                                                    "to_place": "오르세",
                                                },
                                            }
                                        ],
                                    }
                                },
                            },
                        ],
                    }
                },
            },
        )
        self.assertIn(response["trip_id"], TRIP_STATE)

    def test_run_agent_bundle_create_and_flight_book_returns_partial(self) -> None:
        response = run_agent(
            AgentRunRequest(
                message="파리 7월 10일부터 7월 13일까지 일정 짜주고 7월 10일 인천에서 파리 가는 항공권 offer FLT123 예약해줘",
                context={},
            )
        ).model_dump()

        self.assertEqual(response["status"], "PARTIAL")
        self.assertNotIn("clarify", response["data"]["bundle"]["shared_context"])
        _assert_subset(
            self,
            response,
            {
                "intent": "REQUEST_BUNDLE",
                "clarify": {"needed": False},
                "data": {
                    "bundle": {
                        "meta": {
                            "status_counts": {
                                "DONE": 1,
                                "PENDING_CONFIRMATION": 1,
                            }
                        },
                        "results": [
                            {
                                "action_ref": "step_1_create_plan",
                                "status": "DONE",
                            },
                            {
                                "action_ref": "step_2_flight_book",
                                "status": "PENDING_CONFIRMATION",
                                "data": {
                                    "confirmation": {
                                        "needed": True,
                                        "intent": "FLIGHT_BOOK",
                                    }
                                },
                            },
                        ],
                    }
                },
            },
        )
        self.assertIn(response["trip_id"], TRIP_STATE)

    def test_run_agent_bundle_skips_modify_when_create_plan_needs_clarify(self) -> None:
        response = run_agent(
            AgentRunRequest(
                message="파리 일정 짜주고 수정해줘",
                context={},
            )
        ).model_dump()

        self.assertEqual(response["status"], "ASK")
        self.assertNotIn("clarify", response["data"]["bundle"]["shared_context"])
        _assert_subset(
            self,
            response,
            {
                "intent": "REQUEST_BUNDLE",
                "clarify": {"needed": True, "missing_fields": ["dates.days"]},
                "data": {
                    "bundle": {
                        "meta": {"status_counts": {"ASK": 1, "SKIPPED": 1}},
                        "results": [
                            {
                                "action_ref": "step_1_create_plan",
                                "status": "ASK",
                            },
                            {
                                "action_ref": "step_2_modify_plan",
                                "status": "SKIPPED",
                                "blocked_by": ["step_1_create_plan"],
                            },
                        ],
                    }
                },
            },
        )
        self.assertEqual(TRIP_STATE, {})
