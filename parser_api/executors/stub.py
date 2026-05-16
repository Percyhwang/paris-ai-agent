from dataclasses import dataclass

from parser_api.executors.base import ExecutionRequest, ExecutionResult
from parser_api.intents import Intent
from parser_api.services.planning_brief_service import build_unified_planning_brief
from parser_api.services.trip_store import (
    save_create_plan_trip,
    save_modify_plan_trip,
)


def _attach_stub_meta(data: dict, intent: Intent, executor_name: str) -> dict:
    payload = dict(data)
    meta = dict(payload.get("meta") or {})
    meta.setdefault("executor", executor_name)
    meta.setdefault("execution", "stub")
    meta.setdefault("mcp", "not_configured")
    payload["meta"] = meta
    payload.setdefault("intent", intent.value)
    return payload


class CreatePlanExecutor:
    intent = Intent.CREATE_PLAN

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        planning_brief = build_unified_planning_brief(self.intent, request.parsed_payload, request.context)
        trip_id, trip_state = save_create_plan_trip(
            request.parsed_payload.model_dump(),
            extra_state={"planning_brief": planning_brief} if planning_brief else None,
        )
        return ExecutionResult(
            trip_id=trip_id,
            data=_attach_stub_meta(trip_state, self.intent, "create_plan_executor"),
        )


class ModifyPlanExecutor:
    intent = Intent.MODIFY_PLAN

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        planning_brief = build_unified_planning_brief(self.intent, request.parsed_payload, request.context)
        trip_id, trip_state = save_modify_plan_trip(
            request.parsed_payload.model_dump(),
            extra_state={"planning_brief": planning_brief} if planning_brief else None,
        )
        return ExecutionResult(
            trip_id=trip_id,
            data=_attach_stub_meta(trip_state, self.intent, "modify_plan_executor"),
        )


@dataclass(slots=True)
class StubIntentExecutor:
    intent: Intent

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        payload_dict = request.parsed_payload.model_dump()
        payload_dict.pop("clarify", None)

        return ExecutionResult(
            data=_attach_stub_meta(
                {request.data_key: payload_dict},
                self.intent,
                f"{self.intent.value.lower()}_executor",
            )
        )
