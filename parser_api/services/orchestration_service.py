from typing import Any, Optional

from parser_api.executors.base import ExecutionRequest
from parser_api.executors.registry import ExecutorRegistry, executor_registry
from parser_api.intents import Intent
from parser_api.parsers.base import ParsedPayload
from parser_api.parsers.classifier import extract_intent
from parser_api.parsers.registry import ParserRegistry, parser_registry
from parser_api.parsers.workflow.request_bundle.utils import make_action_ref
from parser_api.schemas import (
    AgentRunRequest,
    AgentRunResponse,
    Clarify,
    RequestBundleAction,
    RequestBundlePayload,
)

PAYLOAD_DATA_KEYS = {
    Intent.REQUEST_BUNDLE: "bundle",
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
}


def _build_clarify(parsed_payload: ParsedPayload) -> Clarify:
    clarify = getattr(parsed_payload, "clarify")
    return Clarify(
        needed=clarify.needed,
        missing_fields=list(clarify.missing_fields),
    )


def _strip_clarify(payload_dict: dict) -> dict:
    payload = dict(payload_dict)
    payload.pop("clarify", None)
    return payload


def _strip_nested_clarify(data: dict, data_key: str) -> dict:
    payload = dict(data)
    nested = payload.get(data_key)
    if isinstance(nested, dict):
        nested_payload = dict(nested)
        nested_payload.pop("clarify", None)
        payload[data_key] = nested_payload
    return payload


def _strip_bundle_shared_context_clarify(bundle_payload: dict) -> dict:
    payload = dict(bundle_payload)
    shared_context = payload.get("shared_context")
    if isinstance(shared_context, dict):
        normalized_shared_context = dict(shared_context)
        normalized_shared_context.pop("clarify", None)
        payload["shared_context"] = normalized_shared_context
    return payload


def _has_confirmation_request(data: dict[str, Any]) -> bool:
    confirmation = data.get("confirmation")
    return isinstance(confirmation, dict) and bool(confirmation.get("needed"))


def _needs_confirmation(parsed_payload: ParsedPayload) -> bool:
    return bool(getattr(parsed_payload, "requires_confirmation", False))


def _confirmation_reason(intent: Intent) -> str:
    if intent in {Intent.FLIGHT_BOOK, Intent.HOTEL_BOOK, Intent.MANAGE_BOOKING}:
        return "실제 예약/변경/취소는 확인 단계 이후에 실행되도록 오케스트레이션했습니다."
    return "이 작업은 확인 단계 이후에 실행되도록 오케스트레이션했습니다."


class AgentOrchestrator:
    def __init__(
        self,
        parser_registry: ParserRegistry,
        executor_registry: ExecutorRegistry,
    ) -> None:
        self._parser_registry = parser_registry
        self._executor_registry = executor_registry

    def run(self, payload: AgentRunRequest) -> AgentRunResponse:
        context = dict(payload.context or {})
        intent = extract_intent(payload.message, context)
        return self.run_for_intent(
            intent=intent,
            message=payload.message,
            context=context,
        )

    def run_for_intent(
        self,
        intent: Intent,
        message: str,
        context: Optional[dict[str, Any]] = None,
    ) -> AgentRunResponse:
        parser = self._parser_registry.get(intent)
        if parser is None:
            return AgentRunResponse(
                status="ERROR",
                intent=intent.value,
                trip_id="",
                data={
                    "code": "NOT_IMPLEMENTED",
                    "message": f"{intent.value} is not implemented yet.",
                },
                clarify=Clarify(needed=False, missing_fields=[]),
            )

        parsed_payload = parser.parse(message, context)
        return self.run_parsed_intent(
            intent=intent,
            message=message,
            context=context,
            parsed_payload=parsed_payload,
        )

    def run_parsed_intent(
        self,
        intent: Intent,
        message: str,
        context: Optional[dict[str, Any]],
        parsed_payload: ParsedPayload,
    ) -> AgentRunResponse:
        clarify = _build_clarify(parsed_payload)
        data_key = PAYLOAD_DATA_KEYS[intent]
        payload_dict = _strip_clarify(parsed_payload.model_dump())
        normalized_context = dict(context or {})

        if clarify.needed:
            return AgentRunResponse(
                status="ASK",
                intent=parsed_payload.intent,
                trip_id=self._response_trip_id(intent, parsed_payload),
                data={data_key: payload_dict},
                clarify=clarify,
            )

        if _needs_confirmation(parsed_payload):
            ask_data = {data_key: payload_dict}
            ask_data["confirmation"] = {
                "needed": True,
                "intent": intent.value,
                "reason": _confirmation_reason(intent),
            }
            return AgentRunResponse(
                status="ASK",
                intent=parsed_payload.intent,
                trip_id=self._response_trip_id(intent, parsed_payload),
                data=ask_data,
                clarify=clarify,
            )

        if intent is Intent.REQUEST_BUNDLE:
            return self._run_request_bundle(
                message=message,
                context=normalized_context,
                parsed_payload=parsed_payload,
                clarify=clarify,
                data_key=data_key,
            )

        executor = self._executor_registry.get(intent)
        if executor is None:
            return AgentRunResponse(
                status="ERROR",
                intent=intent.value,
                trip_id="",
                data={
                    "code": "EXECUTOR_NOT_IMPLEMENTED",
                    "message": f"{intent.value} executor is not implemented yet.",
                },
                clarify=clarify,
            )

        result = executor.execute(
            ExecutionRequest(
                intent=intent,
                message=message,
                context=normalized_context,
                parsed_payload=parsed_payload,
                data_key=data_key,
            )
        )
        response_data = _strip_nested_clarify(result.data, data_key)
        return AgentRunResponse(
            status="DONE",
            intent=parsed_payload.intent,
            trip_id=result.trip_id,
            data=response_data,
            clarify=clarify,
        )

    def _response_trip_id(self, intent: Intent, parsed_payload: ParsedPayload) -> str:
        if intent in {Intent.MODIFY_PLAN, Intent.MANAGE_BOOKING, Intent.OPTIMIZE_ROUTE, Intent.TRIP_DIARY}:
            return str(getattr(parsed_payload, "trip_id", "") or "")
        return ""

    def _run_request_bundle(
        self,
        message: str,
        context: dict[str, Any],
        parsed_payload: ParsedPayload,
        clarify: Clarify,
        data_key: str,
    ) -> AgentRunResponse:
        bundle_payload = parsed_payload
        if not isinstance(bundle_payload, RequestBundlePayload):
            return AgentRunResponse(
                status="ERROR",
                intent=Intent.REQUEST_BUNDLE.value,
                trip_id="",
                data={
                    "code": "INVALID_BUNDLE_PAYLOAD",
                    "message": "Parsed payload is not a request bundle payload.",
                },
                clarify=clarify,
            )

        bundle_dict = _strip_bundle_shared_context_clarify(
            _strip_clarify(bundle_payload.model_dump())
        )
        action_results: list[dict[str, Any]] = []
        bundle_status = "DONE"
        current_trip_id = bundle_payload.shared_context.trip_id or ""
        action_statuses: dict[str, str] = {}

        for action in bundle_payload.actions:
            action_ref = make_action_ref(action.intent, action.order)
            blocked_dependencies = [
                dependency
                for dependency in action.depends_on
                if action_statuses.get(dependency) != "DONE"
            ]
            if blocked_dependencies:
                skipped_result = self._build_skipped_action_result(
                    action=action,
                    action_ref=action_ref,
                    blocked_dependencies=blocked_dependencies,
                    action_statuses=action_statuses,
                )
                action_results.append(skipped_result)
                action_statuses[action_ref] = skipped_result["status"]
                continue

            action_response = self._run_bundle_action(
                action=action,
                message=message,
                context=context,
                shared_trip_id=current_trip_id or None,
            )
            action_status = self._resolve_bundle_action_status(action_response)
            action_results.append(
                {
                    "action_ref": action_ref,
                    "intent": action.intent,
                    "order": action.order,
                    "depends_on": list(action.depends_on),
                    "status": action_status,
                    "trip_id": action_response.trip_id,
                    "data": action_response.data,
                    "clarify": action_response.clarify.model_dump(),
                }
            )
            if action_response.trip_id:
                current_trip_id = action_response.trip_id
            action_statuses[action_ref] = action_status

        bundle_dict["results"] = action_results
        bundle_status = self._aggregate_bundle_status(action_results)
        bundle_dict["meta"] = {
            "executor": "request_bundle_orchestrator",
            "execution": "orchestrated",
            "action_count": len(action_results),
            "status_counts": self._count_bundle_statuses(action_results),
        }
        aggregated_clarify = self._aggregate_bundle_clarify(
            bundle_payload=bundle_payload,
            action_results=action_results,
        )

        return AgentRunResponse(
            status=bundle_status,
            intent=Intent.REQUEST_BUNDLE.value,
            trip_id=current_trip_id,
            data={data_key: bundle_dict},
            clarify=aggregated_clarify,
        )

    def _run_bundle_action(
        self,
        action: RequestBundleAction,
        message: str,
        context: dict[str, Any],
        shared_trip_id: Optional[str],
    ) -> AgentRunResponse:
        action_intent = Intent(action.intent)
        action_context = dict(context)
        if shared_trip_id and not action_context.get("trip_id"):
            action_context["trip_id"] = shared_trip_id
        action_context["_bundle_action"] = action.intent

        return self.run_for_intent(
            intent=action_intent,
            message=message,
            context=action_context,
        )

    def _aggregate_bundle_clarify(
        self,
        bundle_payload: RequestBundlePayload,
        action_results: list[dict[str, Any]],
    ) -> Clarify:
        missing_fields: list[str] = list(bundle_payload.clarify.missing_fields)

        for result in action_results:
            clarify = result.get("clarify") or {}
            if not clarify.get("needed"):
                continue
            for field in clarify.get("missing_fields", []):
                if field not in missing_fields:
                    missing_fields.append(field)

        return Clarify(
            needed=bool(missing_fields),
            missing_fields=missing_fields,
        )

    def _resolve_bundle_action_status(self, response: AgentRunResponse) -> str:
        if response.status == "ASK" and _has_confirmation_request(response.data):
            return "PENDING_CONFIRMATION"
        return response.status

    def _build_skipped_action_result(
        self,
        action: RequestBundleAction,
        action_ref: str,
        blocked_dependencies: list[str],
        action_statuses: dict[str, str],
    ) -> dict[str, Any]:
        dependency_states = {
            dependency: action_statuses.get(dependency, "UNKNOWN")
            for dependency in blocked_dependencies
        }
        blocker_text = ", ".join(
            f"{dependency}({dependency_states[dependency]})"
            for dependency in blocked_dependencies
        )
        return {
            "action_ref": action_ref,
            "intent": action.intent,
            "order": action.order,
            "depends_on": list(action.depends_on),
            "status": "SKIPPED",
            "trip_id": "",
            "data": {},
            "clarify": Clarify(needed=False, missing_fields=[]).model_dump(),
            "blocked_by": blocked_dependencies,
            "reason": (
                "선행 작업이 완료되지 않아 실행을 건너뛰었습니다: "
                f"{blocker_text}"
            ),
        }

    def _count_bundle_statuses(self, action_results: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for result in action_results:
            status = str(result["status"])
            counts[status] = counts.get(status, 0) + 1
        return counts

    def _aggregate_bundle_status(self, action_results: list[dict[str, Any]]) -> str:
        statuses = [str(result["status"]) for result in action_results]
        if statuses and all(status == "DONE" for status in statuses):
            return "DONE"

        if any(status == "DONE" for status in statuses):
            return "PARTIAL"

        if any(status in {"ASK", "PENDING_CONFIRMATION"} for status in statuses):
            return "ASK"

        return "ERROR"


default_orchestrator = AgentOrchestrator(
    parser_registry=parser_registry,
    executor_registry=executor_registry,
)
