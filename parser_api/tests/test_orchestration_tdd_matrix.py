from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from itertools import product

from parser_api.executors.base import ExecutionRequest, ExecutionResult
from parser_api.executors.registry import ExecutorRegistry
from parser_api.intents import Intent
from parser_api.parsers.registry import ParserRegistry
from parser_api.schemas import Clarify, RequestBundleAction, RequestBundlePayload
from parser_api.services.orchestration_service import AgentOrchestrator

RESPONSE_TRIP_ID_INTENTS = {
    Intent.MODIFY_PLAN,
    Intent.MANAGE_BOOKING,
    Intent.OPTIMIZE_ROUTE,
    Intent.TRIP_DIARY,
}

DIRECT_INTENTS = (
    Intent.CREATE_PLAN,
    Intent.MODIFY_PLAN,
    Intent.FLIGHT_SEARCH,
    Intent.FLIGHT_BOOK,
    Intent.HOTEL_SEARCH,
    Intent.HOTEL_BOOK,
    Intent.ESTIMATE_BUDGET,
    Intent.MANAGE_BOOKING,
    Intent.OPTIMIZE_ROUTE,
    Intent.RECOMMEND_VENUE,
    Intent.MANAGE_TRIP,
    Intent.USER_PROFILE,
    Intent.TRAVEL_STYLE,
    Intent.TRIP_DIARY,
)

DIRECT_OUTCOMES = (
    "done",
    "done_nested",
    "done_with_trip",
    "ask",
    "ask_with_trip",
    "confirm",
    "error",
)

BUNDLE_OUTCOMES = (
    "done",
    "done_nested",
    "done_generated_trip",
    "ask",
    "confirm",
    "error",
)


@dataclass(slots=True)
class FakeParsedPayload:
    intent: str
    clarify: Clarify = field(default_factory=Clarify)
    trip_id: str | None = None
    requires_confirmation: bool = False
    payload_fields: dict = field(default_factory=dict)

    def model_dump(self) -> dict:
        payload = {"intent": self.intent, **self.payload_fields}
        if self.trip_id is not None:
            payload["trip_id"] = self.trip_id
        if self.requires_confirmation:
            payload["requires_confirmation"] = True
        payload["clarify"] = self.clarify.model_dump()
        return payload


@dataclass(slots=True)
class ScenarioParser:
    intent: Intent
    outcome: str
    read_trip_id_from_context: bool = False
    payload_trip_id: str | None = None

    def parse(self, message: str, context: dict | None = None) -> FakeParsedPayload:
        del message
        trip_id = self.payload_trip_id
        if self.read_trip_id_from_context:
            trip_id = str((context or {}).get("trip_id") or "") or None

        clarify = Clarify(needed=False, missing_fields=[])
        if self.outcome == "ask":
            clarify = Clarify(
                needed=True,
                missing_fields=[f"{self.intent.value.lower()}.missing"],
            )

        return FakeParsedPayload(
            intent=self.intent.value,
            clarify=clarify,
            trip_id=trip_id,
            requires_confirmation=self.outcome == "confirm",
            payload_fields={"payload_source": self.intent.value.lower()},
        )


@dataclass(slots=True)
class ScenarioExecutor:
    intent: Intent
    outcome: str
    generated_trip_id: str = ""
    echo_context_trip_id: bool = False

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        trip_id = self.generated_trip_id
        if self.echo_context_trip_id:
            trip_id = str(request.context.get("trip_id") or "")

        payload = {
            request.data_key: {
                "payload_source": self.intent.value.lower(),
            }
        }
        if trip_id:
            payload[request.data_key]["trip_id"] = trip_id
        if self.outcome == "done_nested":
            payload[request.data_key]["clarify"] = {
                "needed": False,
                "missing_fields": [],
            }

        return ExecutionResult(trip_id=trip_id, data=payload)


def _bundle_action_status(outcome: str) -> str:
    if outcome == "ask":
        return "ASK"
    if outcome == "confirm":
        return "PENDING_CONFIRMATION"
    if outcome == "error":
        return "ERROR"
    return "DONE"


def _aggregate_bundle_status(statuses: list[str]) -> str:
    if statuses and all(status == "DONE" for status in statuses):
        return "DONE"
    if any(status == "DONE" for status in statuses):
        return "PARTIAL"
    if any(status in {"ASK", "PENDING_CONFIRMATION"} for status in statuses):
        return "ASK"
    return "ERROR"


class OrchestrationTDDMatrixTests(unittest.TestCase):
    def test_run_parsed_intent_direct_matrix(self) -> None:
        for intent, outcome in product(DIRECT_INTENTS, DIRECT_OUTCOMES):
            with self.subTest(intent=intent.value, outcome=outcome):
                orchestrator = AgentOrchestrator(
                    parser_registry=ParserRegistry(),
                    executor_registry=self._build_direct_executor_registry(intent, outcome),
                )
                parsed_payload = self._build_direct_payload(intent, outcome)

                response = orchestrator.run_parsed_intent(
                    intent=intent,
                    message=f"{intent.value} matrix test",
                    context={"trip_id": "trip-context-direct"},
                    parsed_payload=parsed_payload,
                )

                expected_trip_id = ""
                if outcome == "done_with_trip":
                    expected_trip_id = "trip-direct-result"
                elif outcome == "ask_with_trip" and intent in RESPONSE_TRIP_ID_INTENTS:
                    expected_trip_id = "trip-direct-payload"
                elif outcome == "confirm" and intent in RESPONSE_TRIP_ID_INTENTS:
                    expected_trip_id = "trip-direct-payload"

                expected_status = "DONE"
                if outcome in {"ask", "ask_with_trip", "confirm"}:
                    expected_status = "ASK"
                elif outcome == "error":
                    expected_status = "ERROR"

                self.assertEqual(response.status, expected_status)
                self.assertEqual(response.intent, intent.value)
                self.assertEqual(response.trip_id, expected_trip_id)

                if outcome in {"ask", "ask_with_trip"}:
                    self.assertTrue(response.clarify.needed)
                    self.assertIn(
                        f"{intent.value.lower()}.missing",
                        response.clarify.missing_fields,
                    )
                else:
                    self.assertFalse(response.clarify.needed)

                if outcome == "confirm":
                    self.assertTrue(response.data["confirmation"]["needed"])
                    expected_reason = (
                        "실제 예약/변경/취소는 확인 단계 이후에 실행되도록 오케스트레이션했습니다."
                        if intent in {
                            Intent.FLIGHT_BOOK,
                            Intent.HOTEL_BOOK,
                            Intent.MANAGE_BOOKING,
                        }
                        else "이 작업은 확인 단계 이후에 실행되도록 오케스트레이션했습니다."
                    )
                    self.assertEqual(response.data["confirmation"]["reason"], expected_reason)

                if outcome == "error":
                    self.assertEqual(
                        response.data["code"],
                        "EXECUTOR_NOT_IMPLEMENTED",
                    )
                    continue

                data_key = self._data_key(intent)
                self.assertIn(data_key, response.data)
                if outcome == "done_nested":
                    self.assertNotIn("clarify", response.data[data_key])
                if outcome == "done_with_trip":
                    self.assertEqual(response.data[data_key]["trip_id"], "trip-direct-result")

    def test_run_parsed_intent_bundle_matrix(self) -> None:
        shared_trip_options = ("", "trip-bundle-shared")
        cases = product(
            BUNDLE_OUTCOMES,
            BUNDLE_OUTCOMES,
            (False, True),
            shared_trip_options,
        )

        for first_outcome, second_outcome, depends_on_first, shared_trip_id in cases:
            case_name = (
                f"{first_outcome}|{second_outcome}|"
                f"depends={depends_on_first}|shared={bool(shared_trip_id)}"
            )
            with self.subTest(case=case_name):
                parser_registry = ParserRegistry()
                parser_registry.register(
                    ScenarioParser(intent=Intent.CREATE_PLAN, outcome=first_outcome)
                )
                parser_registry.register(
                    ScenarioParser(
                        intent=Intent.MODIFY_PLAN,
                        outcome=second_outcome,
                        read_trip_id_from_context=True,
                    )
                )

                executor_registry = ExecutorRegistry()
                self._register_bundle_executor(
                    executor_registry,
                    intent=Intent.CREATE_PLAN,
                    outcome=first_outcome,
                    generated_trip_id="trip-generated-1",
                    echo_context_trip_id=False,
                )
                self._register_bundle_executor(
                    executor_registry,
                    intent=Intent.MODIFY_PLAN,
                    outcome=second_outcome,
                    generated_trip_id="trip-generated-2",
                    echo_context_trip_id=second_outcome in {"done", "done_nested"},
                )

                orchestrator = AgentOrchestrator(
                    parser_registry=parser_registry,
                    executor_registry=executor_registry,
                )
                payload = RequestBundlePayload(
                    actions=[
                        RequestBundleAction(intent="CREATE_PLAN", order=1),
                        RequestBundleAction(
                            intent="MODIFY_PLAN",
                            order=2,
                            depends_on=["step_1_create_plan"] if depends_on_first else [],
                        ),
                    ]
                )
                payload.shared_context.trip_id = shared_trip_id or None
                payload.clarify = Clarify(needed=False, missing_fields=[])

                response = orchestrator.run_parsed_intent(
                    intent=Intent.REQUEST_BUNDLE,
                    message="bundle matrix test",
                    context={},
                    parsed_payload=payload,
                )

                first_status = _bundle_action_status(first_outcome)
                second_should_skip = depends_on_first and first_status != "DONE"
                second_status = (
                    "SKIPPED"
                    if second_should_skip
                    else _bundle_action_status(second_outcome)
                )
                expected_bundle_status = _aggregate_bundle_status(
                    [first_status, second_status]
                )

                self.assertEqual(response.status, expected_bundle_status)
                self.assertEqual(response.intent, Intent.REQUEST_BUNDLE.value)
                self.assertNotIn(
                    "clarify",
                    response.data["bundle"]["shared_context"],
                )

                results = response.data["bundle"]["results"]
                self.assertEqual(len(results), 2)
                self.assertEqual(results[0]["status"], first_status)
                self.assertEqual(results[1]["status"], second_status)
                self.assertEqual(
                    response.data["bundle"]["meta"]["status_counts"],
                    self._count_statuses([first_status, second_status]),
                )

                if first_outcome == "done_nested":
                    self.assertNotIn("clarify", results[0]["data"]["plan"])

                current_trip_id = shared_trip_id
                if first_outcome == "done_generated_trip":
                    current_trip_id = "trip-generated-1"

                expected_second_trip_id = ""
                if not second_should_skip:
                    if second_outcome in {"done", "done_nested", "ask", "confirm"}:
                        expected_second_trip_id = current_trip_id
                    elif second_outcome == "done_generated_trip":
                        expected_second_trip_id = "trip-generated-2"

                expected_response_trip_id = current_trip_id
                if expected_second_trip_id:
                    expected_response_trip_id = expected_second_trip_id

                self.assertEqual(response.trip_id, expected_response_trip_id)

                if second_should_skip:
                    self.assertEqual(
                        results[1]["blocked_by"],
                        ["step_1_create_plan"],
                    )
                else:
                    self.assertEqual(results[1]["trip_id"], expected_second_trip_id)
                    if second_outcome == "done_nested":
                        self.assertNotIn("clarify", results[1]["data"]["modify"])

                clarify_needed = any(
                    status == "ASK" for status in (first_status, second_status)
                )
                self.assertEqual(response.clarify.needed, clarify_needed)

    def _build_direct_payload(self, intent: Intent, outcome: str) -> FakeParsedPayload:
        clarify = Clarify(needed=False, missing_fields=[])
        payload_trip_id = None
        requires_confirmation = False

        if outcome in {"ask", "ask_with_trip"}:
            clarify = Clarify(
                needed=True,
                missing_fields=[f"{intent.value.lower()}.missing"],
            )
        if outcome in {"ask_with_trip", "confirm"}:
            payload_trip_id = "trip-direct-payload"
        if outcome == "confirm":
            requires_confirmation = True

        return FakeParsedPayload(
            intent=intent.value,
            clarify=clarify,
            trip_id=payload_trip_id,
            requires_confirmation=requires_confirmation,
            payload_fields={"payload_source": intent.value.lower()},
        )

    def _build_direct_executor_registry(
        self,
        intent: Intent,
        outcome: str,
    ) -> ExecutorRegistry:
        registry = ExecutorRegistry()
        if outcome in {"error", "ask", "ask_with_trip", "confirm"}:
            return registry

        registry.register(
            ScenarioExecutor(
                intent=intent,
                outcome=outcome,
                generated_trip_id=(
                    "trip-direct-result" if outcome == "done_with_trip" else ""
                ),
            )
        )
        return registry

    def _register_bundle_executor(
        self,
        registry: ExecutorRegistry,
        intent: Intent,
        outcome: str,
        generated_trip_id: str,
        echo_context_trip_id: bool,
    ) -> None:
        if outcome in {"error", "ask", "confirm"}:
            return

        registry.register(
            ScenarioExecutor(
                intent=intent,
                outcome=(
                    "done_nested" if outcome == "done_nested" else "done"
                ),
                generated_trip_id=(
                    generated_trip_id if outcome == "done_generated_trip" else ""
                ),
                echo_context_trip_id=echo_context_trip_id,
            )
        )

    def _count_statuses(self, statuses: list[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for status in statuses:
            counts[status] = counts.get(status, 0) + 1
        return counts

    def _data_key(self, intent: Intent) -> str:
        return {
            Intent.CREATE_PLAN: "plan",
            Intent.MODIFY_PLAN: "modify",
            Intent.FLIGHT_SEARCH: "flight_search",
            Intent.FLIGHT_BOOK: "flight_book",
            Intent.HOTEL_SEARCH: "hotel_search",
            Intent.HOTEL_BOOK: "hotel_book",
            Intent.ESTIMATE_BUDGET: "budget_estimate",
            Intent.MANAGE_BOOKING: "manage_booking",
            Intent.OPTIMIZE_ROUTE: "route_optimization",
            Intent.RECOMMEND_VENUE: "venue_recommendation",
            Intent.MANAGE_TRIP: "manage_trip",
            Intent.USER_PROFILE: "user_profile",
            Intent.TRAVEL_STYLE: "travel_style",
            Intent.TRIP_DIARY: "trip_diary",
        }[intent]

