from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.agent_action_schema import AgentActionPlan, ParserValidationResult


class HotelSearchRequest(BaseModel):
    destination: str = "Paris"
    check_in: str | None = None
    check_out: str | None = None
    location_preference: str | None = None
    budget: int | None = Field(default=None, ge=0)
    guest_count: int = Field(default=1, ge=1)
    room_count: int = Field(default=1, ge=1)
    amenities: list[str] = Field(default_factory=list)
    rating_preference: int | None = Field(default=None, ge=1, le=5)
    hotel_style: list[str] = Field(default_factory=list)


def parse_hotel_search_action(action: AgentActionPlan) -> ParserValidationResult:
    args: dict[str, Any] = dict(action.arguments or {})
    request = HotelSearchRequest(
        destination=str(args.get("destination") or "Paris"),
        check_in=args.get("check_in") or args.get("checkin") or args.get("check_in_date"),
        check_out=args.get("check_out") or args.get("checkout") or args.get("check_out_date"),
        location_preference=args.get("location_preference") or args.get("area") or args.get("landmark"),
        budget=args.get("budget") or args.get("max_price_per_night"),
        guest_count=args.get("guest_count") or args.get("guests") or 1,
        room_count=args.get("room_count") or args.get("rooms") or 1,
        amenities=[str(value) for value in args.get("amenities") or [] if str(value).strip()],
        rating_preference=args.get("rating_preference") or args.get("star_rating"),
        hotel_style=[str(value) for value in args.get("hotel_style") or [] if str(value).strip()],
    )
    missing = []
    if not request.check_in:
        missing.append("check_in")
    if not request.check_out:
        missing.append("check_out")
    return ParserValidationResult(
        valid=not missing,
        action=action,
        normalized_arguments=request.model_dump(mode="json"),
        missing_required_fields=missing,
    )

