from __future__ import annotations

from app.schemas.agent_action_schema import AgentActionPlan, ParserValidationResult


def parse_select_flight_action(action: AgentActionPlan) -> ParserValidationResult:
    args = dict(action.arguments or {})
    missing = []
    if not args.get("trip_id"):
        missing.append("trip_id")
    if args.get("selected_candidate_id") is None and args.get("index") is None:
        missing.append("selected_candidate_id")
    return ParserValidationResult(
        valid=not missing,
        action=action,
        normalized_arguments=args,
        missing_required_fields=missing,
    )

