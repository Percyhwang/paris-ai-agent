from __future__ import annotations

from app.schemas.agent_action_schema import AgentActionPlan, ParserValidationResult
from app.schemas.trips import TripAgentModifyRequest


def parse_modify_plan_action(
    action: AgentActionPlan,
    fallback_request: TripAgentModifyRequest | None = None,
) -> ParserValidationResult:
    args = dict(action.arguments or {})
    prompt = str(args.get("prompt") or args.get("user_request") or action.raw_text or "").strip()
    target_day = args.get("target_day")
    if fallback_request is not None:
        prompt = fallback_request.prompt
        target_day = fallback_request.target_day

    missing = []
    if not prompt:
        missing.append("prompt")

    if missing:
        return ParserValidationResult(valid=False, action=action, missing_required_fields=missing)

    request = TripAgentModifyRequest(prompt=prompt, target_day=target_day)
    return ParserValidationResult(
        valid=True,
        action=action,
        normalized_arguments=request.model_dump(mode="json"),
    )

