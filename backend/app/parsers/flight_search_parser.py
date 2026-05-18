from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.agent_action_schema import AgentActionPlan, ParserValidationResult


class FlightSearchRequest(BaseModel):
    origin: str | None = None
    destination: str = "Paris"
    departure_date: str | None = None
    return_date: str | None = None
    passengers: int = Field(default=1, ge=1)
    max_layovers: int | None = Field(default=None, ge=0)
    budget: int | None = Field(default=None, ge=0)
    airline_preference: list[str] = Field(default_factory=list)
    time_preference: list[str] = Field(default_factory=list)


def parse_flight_search_action(action: AgentActionPlan) -> ParserValidationResult:
    args: dict[str, Any] = dict(action.arguments or {})
    request = FlightSearchRequest(
        origin=args.get("origin"),
        destination=str(args.get("destination") or "Paris"),
        departure_date=args.get("departure_date") or args.get("depart_date"),
        return_date=args.get("return_date"),
        passengers=args.get("passengers") or args.get("adults") or 1,
        max_layovers=args.get("max_layovers"),
        budget=args.get("budget") or args.get("max_price"),
        airline_preference=[str(value) for value in args.get("airline_preference") or [] if str(value).strip()],
        time_preference=[str(value) for value in args.get("time_preference") or [] if str(value).strip()],
    )
    missing = []
    if not request.origin:
        missing.append("origin")
    if not request.departure_date:
        missing.append("departure_date")
    return ParserValidationResult(
        valid=not missing,
        action=action,
        normalized_arguments=request.model_dump(mode="json"),
        missing_required_fields=missing,
    )

