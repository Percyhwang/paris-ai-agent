from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ConstraintSpec(BaseModel):
    id: str
    type: str
    value: Any
    priority: Literal["hard", "soft"] = "soft"
    source: Literal["user", "parser", "system", "fallback"] = "user"
    satisfied: bool = False


class PlanningBriefPayload(BaseModel):
    intent: str
    trip_days: int | None = None
    destination: str | None = None
    must_include: list[str] = Field(default_factory=list)
    must_avoid: list[str] = Field(default_factory=list)
    preferred_time_slots: list[str] = Field(default_factory=list)
    meal_preference: list[str] = Field(default_factory=list)
    night_view_required: bool = False
    pace: str = "normal"
    travel_style: list[str] = Field(default_factory=list)
    budget_range: dict[str, Any] = Field(default_factory=dict)
    hotel_area_preference: str | None = None
    transport_preference: str = "both"
    start_time: str | None = None
    end_time: str | None = None
    hard_constraints: list[ConstraintSpec] = Field(default_factory=list)
    soft_constraints: list[ConstraintSpec] = Field(default_factory=list)
    strict_constraints: bool = False
    locked_stops: list[dict[str, Any]] = Field(default_factory=list)
    preferred_blueprints: list[str] = Field(default_factory=list)
    quality_focus: str | None = None
