from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.schemas.agent_action_schema import AgentActionPlan, ParserValidationResult


def validate_agent_action(raw_action: dict[str, Any] | AgentActionPlan) -> ParserValidationResult:
    if isinstance(raw_action, AgentActionPlan):
        action = raw_action
        return ParserValidationResult(valid=True, action=action, normalized_arguments=dict(action.arguments))

    try:
        action = AgentActionPlan.model_validate(raw_action)
    except ValidationError as exc:
        fallback = AgentActionPlan(
            intent="GENERAL_TRAVEL_QA",
            action="clarify",
            confidence=0.0,
            needs_clarification=True,
            missing_required_fields=["intent"],
            clarification_question="요청을 어떤 여행 작업으로 처리할지 다시 알려주세요.",
            concise_decision_summary="Controller output failed schema validation.",
            raw_text=str(raw_action),
        )
        return ParserValidationResult(
            valid=False,
            action=fallback,
            missing_required_fields=["intent"],
            warnings=[str(exc)],
        )

    return ParserValidationResult(valid=True, action=action, normalized_arguments=dict(action.arguments))

