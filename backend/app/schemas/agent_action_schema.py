from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AgentIntent(str, Enum):
    CREATE_ITINERARY = "CREATE_ITINERARY"
    MODIFY_ITINERARY = "MODIFY_ITINERARY"
    SEARCH_HOTEL = "SEARCH_HOTEL"
    SEARCH_FLIGHT = "SEARCH_FLIGHT"
    SEARCH_PLACE = "SEARCH_PLACE"
    SELECT_HOTEL = "SELECT_HOTEL"
    SELECT_FLIGHT = "SELECT_FLIGHT"
    UPDATE_PREFERENCE = "UPDATE_PREFERENCE"
    GENERAL_TRAVEL_QA = "GENERAL_TRAVEL_QA"


class AgentActionPlan(BaseModel):
    intent: AgentIntent
    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_clarification: bool = False
    missing_required_fields: list[str] = Field(default_factory=list)
    clarification_question: str | None = None
    concise_decision_summary: str = ""
    raw_text: str = ""
    source: str = "deterministic_controller"


class ParserValidationResult(BaseModel):
    valid: bool
    action: AgentActionPlan
    normalized_arguments: dict[str, Any] = Field(default_factory=dict)
    missing_required_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

