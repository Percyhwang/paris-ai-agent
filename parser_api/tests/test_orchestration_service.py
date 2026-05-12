import unittest

from parser_api.executors.base import ExecutionRequest, ExecutionResult
from parser_api.executors.registry import ExecutorRegistry
from parser_api.intents import Intent
from parser_api.schemas import (
    Clarify,
    CreatePlanPayload,
    EstimateBudgetPayload,
    FlightBookPayload,
    ModifyPlanPayload,
    RequestBundleAction,
    RequestBundlePayload,
)
from parser_api.services.orchestration_service import AgentOrchestrator


class DummyParser:
    def __init__(self, payload) -> None:
        self._payload = payload

    def parse(self, message: str, context: dict | None = None):
        del message, context
        return self._payload


class ContextAwareParser:
    def parse(self, message: str, context: dict | None = None):
        del message
        payload = ModifyPlanPayload(trip_id=(context or {}).get("trip_id"))
        payload.clarify = Clarify(needed=False, missing_fields=[])
        return payload


class DummyParserRegistry:
    def __init__(self, mapping: dict[Intent, object]) -> None:
        self._mapping = mapping

    def get(self, intent: Intent):
        return self._mapping.get(intent)


class DummyExecutor:
    def __init__(self, intent: Intent, trip_id: str = "", data: dict | None = None) -> None:
        self.intent = intent
        self.trip_id = trip_id
        self.data = data or {}

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        del request
        return ExecutionResult(trip_id=self.trip_id, data=self.data)


class ContextEchoExecutor:
    def __init__(self, intent: Intent) -> None:
        self.intent = intent

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        trip_id = str(request.context.get("trip_id") or "")
        return ExecutionResult(
            trip_id=trip_id,
            data={
                request.data_key: {
                    "trip_id": trip_id,
                    "clarify": {"needed": False, "missing_fields": []},
                }
            },
        )


class OrchestrationServiceTests(unittest.TestCase):
    def test_run_parsed_intent_executes_regular_executor(self) -> None:
        registry = ExecutorRegistry()
        registry.register(
            DummyExecutor(
                intent=Intent.CREATE_PLAN,
                trip_id="trip-1",
                data={"plan": {"destination": {"city": "Paris"}}},
            )
        )
        orchestrator = AgentOrchestrator(
            parser_registry=DummyParserRegistry({}),
            executor_registry=registry,
        )

        response = orchestrator.run_parsed_intent(
            intent=Intent.CREATE_PLAN,
            message="파리 여행 일정 짜줘",
            context={},
            parsed_payload=CreatePlanPayload(clarify=Clarify(needed=False, missing_fields=[])),
        )

        self.assertEqual(response.status, "DONE")
        self.assertEqual(response.trip_id, "trip-1")
        self.assertIn("plan", response.data)

    def test_run_parsed_intent_strips_nested_clarify_from_executor_result(self) -> None:
        registry = ExecutorRegistry()
        registry.register(
            DummyExecutor(
                intent=Intent.CREATE_PLAN,
                trip_id="trip-1",
                data={
                    "intent": "CREATE_PLAN",
                    "plan": {
                        "destination": {"city": "Paris"},
                        "clarify": {"needed": False, "missing_fields": []},
                    },
                },
            )
        )
        orchestrator = AgentOrchestrator(
            parser_registry=DummyParserRegistry({}),
            executor_registry=registry,
        )

        response = orchestrator.run_parsed_intent(
            intent=Intent.CREATE_PLAN,
            message="파리 여행 일정 짜줘",
            context={},
            parsed_payload=CreatePlanPayload(clarify=Clarify(needed=False, missing_fields=[])),
        )

        self.assertEqual(response.status, "DONE")
        self.assertNotIn("clarify", response.data["plan"])

    def test_run_parsed_intent_returns_ask_for_confirmation(self) -> None:
        orchestrator = AgentOrchestrator(
            parser_registry=DummyParserRegistry({}),
            executor_registry=ExecutorRegistry(),
        )
        payload = FlightBookPayload(offer_ref="flt_offer_123")
        payload.clarify = Clarify(needed=False, missing_fields=[])

        response = orchestrator.run_parsed_intent(
            intent=Intent.FLIGHT_BOOK,
            message="항공권 예약해줘",
            context={},
            parsed_payload=payload,
        )

        self.assertEqual(response.status, "ASK")
        self.assertTrue(response.data["confirmation"]["needed"])
        self.assertEqual(response.data["confirmation"]["intent"], "FLIGHT_BOOK")

    def test_run_parsed_intent_executes_bundle_actions(self) -> None:
        parser_registry = DummyParserRegistry(
            {
                Intent.CREATE_PLAN: DummyParser(CreatePlanPayload()),
                Intent.ESTIMATE_BUDGET: DummyParser(EstimateBudgetPayload()),
            }
        )
        executor_registry = ExecutorRegistry()
        executor_registry.register(
            DummyExecutor(
                intent=Intent.CREATE_PLAN,
                trip_id="trip-9",
                data={"plan": {"destination": {"city": "Paris"}}},
            )
        )
        executor_registry.register(
            DummyExecutor(
                intent=Intent.ESTIMATE_BUDGET,
                data={"budget_estimate": {"total": 3000000}},
            )
        )
        orchestrator = AgentOrchestrator(
            parser_registry=parser_registry,
            executor_registry=executor_registry,
        )
        payload = RequestBundlePayload(
            actions=[
                RequestBundleAction(intent="CREATE_PLAN", order=1),
                RequestBundleAction(intent="ESTIMATE_BUDGET", order=2),
            ]
        )

        response = orchestrator.run_parsed_intent(
            intent=Intent.REQUEST_BUNDLE,
            message="파리 일정 짜주고 예산도 계산해줘",
            context={},
            parsed_payload=payload,
        )

        self.assertEqual(response.status, "DONE")
        self.assertEqual(response.trip_id, "trip-9")
        self.assertEqual(len(response.data["bundle"]["results"]), 2)
        self.assertEqual(response.data["bundle"]["results"][0]["intent"], "CREATE_PLAN")
        self.assertEqual(response.data["bundle"]["results"][1]["intent"], "ESTIMATE_BUDGET")

    def test_run_parsed_intent_aggregates_bundle_clarify(self) -> None:
        parser_registry = DummyParserRegistry(
            {
                Intent.CREATE_PLAN: DummyParser(
                    CreatePlanPayload(
                        clarify=Clarify(needed=True, missing_fields=["dates.days"])
                    )
                ),
            }
        )
        orchestrator = AgentOrchestrator(
            parser_registry=parser_registry,
            executor_registry=ExecutorRegistry(),
        )
        payload = RequestBundlePayload(
            actions=[RequestBundleAction(intent="CREATE_PLAN", order=1)]
        )

        response = orchestrator.run_parsed_intent(
            intent=Intent.REQUEST_BUNDLE,
            message="파리 여행 일정 짜줘",
            context={},
            parsed_payload=payload,
        )

        self.assertEqual(response.status, "ASK")
        self.assertTrue(response.clarify.needed)
        self.assertEqual(response.clarify.missing_fields, ["dates.days"])

    def test_run_parsed_intent_propagates_trip_id_between_bundle_actions(self) -> None:
        parser_registry = DummyParserRegistry(
            {
                Intent.CREATE_PLAN: DummyParser(CreatePlanPayload()),
                Intent.MODIFY_PLAN: ContextAwareParser(),
            }
        )
        executor_registry = ExecutorRegistry()
        executor_registry.register(
            DummyExecutor(
                intent=Intent.CREATE_PLAN,
                trip_id="trip-42",
                data={"plan": {"destination": {"city": "Paris"}}},
            )
        )
        executor_registry.register(ContextEchoExecutor(intent=Intent.MODIFY_PLAN))
        orchestrator = AgentOrchestrator(
            parser_registry=parser_registry,
            executor_registry=executor_registry,
        )
        payload = RequestBundlePayload(
            actions=[
                RequestBundleAction(intent="CREATE_PLAN", order=1),
                RequestBundleAction(intent="MODIFY_PLAN", order=2),
            ]
        )

        response = orchestrator.run_parsed_intent(
            intent=Intent.REQUEST_BUNDLE,
            message="파리 일정 짜주고 수정해줘",
            context={},
            parsed_payload=payload,
        )

        self.assertEqual(response.status, "DONE")
        self.assertEqual(response.trip_id, "trip-42")
        self.assertEqual(response.data["bundle"]["results"][1]["trip_id"], "trip-42")
        self.assertEqual(
            response.data["bundle"]["results"][1]["data"]["modify"]["trip_id"],
            "trip-42",
        )

    def test_run_parsed_intent_skips_blocked_dependent_actions(self) -> None:
        parser_registry = DummyParserRegistry(
            {
                Intent.CREATE_PLAN: DummyParser(
                    CreatePlanPayload(
                        clarify=Clarify(needed=True, missing_fields=["dates.days"])
                    )
                ),
            }
        )
        orchestrator = AgentOrchestrator(
            parser_registry=parser_registry,
            executor_registry=ExecutorRegistry(),
        )
        payload = RequestBundlePayload(
            actions=[
                RequestBundleAction(intent="CREATE_PLAN", order=1),
                RequestBundleAction(
                    intent="MODIFY_PLAN",
                    order=2,
                    depends_on=["step_1_create_plan"],
                ),
            ]
        )

        response = orchestrator.run_parsed_intent(
            intent=Intent.REQUEST_BUNDLE,
            message="파리 여행 일정 짜주고 수정해줘",
            context={},
            parsed_payload=payload,
        )

        self.assertEqual(response.status, "ASK")
        self.assertEqual(response.data["bundle"]["results"][0]["status"], "ASK")
        self.assertEqual(response.data["bundle"]["results"][1]["status"], "SKIPPED")
        self.assertEqual(
            response.data["bundle"]["results"][1]["blocked_by"],
            ["step_1_create_plan"],
        )

    def test_run_parsed_intent_returns_partial_for_mixed_bundle_results(self) -> None:
        parser_registry = DummyParserRegistry(
            {
                Intent.CREATE_PLAN: DummyParser(CreatePlanPayload()),
                Intent.FLIGHT_BOOK: DummyParser(
                    FlightBookPayload(
                        offer_ref="flt_offer_123",
                        requires_confirmation=True,
                    )
                ),
            }
        )
        executor_registry = ExecutorRegistry()
        executor_registry.register(
            DummyExecutor(
                intent=Intent.CREATE_PLAN,
                trip_id="trip-51",
                data={"plan": {"destination": {"city": "Paris"}}},
            )
        )
        orchestrator = AgentOrchestrator(
            parser_registry=parser_registry,
            executor_registry=executor_registry,
        )
        payload = RequestBundlePayload(
            actions=[
                RequestBundleAction(intent="CREATE_PLAN", order=1),
                RequestBundleAction(intent="FLIGHT_BOOK", order=2),
            ]
        )

        response = orchestrator.run_parsed_intent(
            intent=Intent.REQUEST_BUNDLE,
            message="일정 만들고 항공권 예약해줘",
            context={},
            parsed_payload=payload,
        )

        self.assertEqual(response.status, "PARTIAL")
        self.assertEqual(response.data["bundle"]["results"][0]["status"], "DONE")
        self.assertEqual(
            response.data["bundle"]["results"][1]["status"],
            "PENDING_CONFIRMATION",
        )
