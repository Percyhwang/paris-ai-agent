from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.schemas.agent_action_schema import AgentActionPlan, ParserValidationResult
from app.schemas.trips import TripGenerateRequest


def parse_create_plan_action(
    action: AgentActionPlan,
    fallback_request: TripGenerateRequest | None = None,
) -> ParserValidationResult:
    args: dict[str, Any] = dict(action.arguments or {})
    prompt = str(args.get("prompt") or args.get("user_request") or action.raw_text or "").strip()
    start_date = args.get("start_date")
    end_date = args.get("end_date")
    total_days = args.get("total_days") or args.get("days")
    style_tags = _string_list(args.get("style_tags") or args.get("preferences") or [])

    if fallback_request is not None:
        prompt = fallback_request.prompt
        start_date = fallback_request.start_date
        end_date = fallback_request.end_date
        total_days = fallback_request.total_days
        style_tags = list(fallback_request.style_tags or [])

    missing = []
    if len(prompt) < 3:
        missing.append("prompt")

    if missing:
        return ParserValidationResult(valid=False, action=action, missing_required_fields=missing)

    try:
        request = TripGenerateRequest(
            prompt=prompt,
            start_date=start_date,
            end_date=end_date,
            total_days=total_days,
            style_tags=style_tags,
        )
    except ValidationError as exc:
        return ParserValidationResult(
            valid=False,
            action=action,
            normalized_arguments={
                "prompt": prompt,
                "start_date": start_date,
                "end_date": end_date,
                "total_days": total_days,
                "style_tags": style_tags,
            },
            warnings=[str(exc)],
        )

    return ParserValidationResult(
        valid=True,
        action=action,
        normalized_arguments=request.model_dump(mode="json"),
    )


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []

