from __future__ import annotations

from typing import Any

from app.schemas.agent_action_schema import AgentActionPlan, ParserValidationResult
from app.schemas.trips import TripGenerateRequest


def parse_create_plan_action(
    action: AgentActionPlan,
    fallback_request: TripGenerateRequest | None = None,
) -> ParserValidationResult:
    args = dict(action.arguments or {})
    prompt = str(args.get("prompt") or args.get("user_request") or action.raw_text or "").strip()
    if fallback_request is not None:
        prompt = fallback_request.prompt
        start_date = fallback_request.start_date
        end_date = fallback_request.end_date
        total_days = fallback_request.total_days
        style_tags = list(fallback_request.style_tags or [])
    else:
        start_date = args.get("start_date")
        end_date = args.get("end_date")
        total_days = args.get("total_days") or args.get("days")
        style_tags = [str(value) for value in args.get("style_tags") or args.get("interests") or [] if str(value).strip()]

    missing = []
    if not prompt:
        missing.append("prompt")

    if missing:
        return ParserValidationResult(
            valid=False,
            action=action,
            missing_required_fields=missing,
            warnings=["CREATE_ITINERARY action is missing required fields."],
        )

    request = TripGenerateRequest(
        prompt=prompt,
        start_date=start_date,
        end_date=end_date,
        total_days=total_days,
        style_tags=style_tags,
    )
    return ParserValidationResult(
        valid=True,
        action=action,
        normalized_arguments=request.model_dump(mode="json"),
    )

