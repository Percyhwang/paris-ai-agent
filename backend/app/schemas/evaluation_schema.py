from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PlanFailure(BaseModel):
    failure_type: str
    severity: Literal["hard", "soft"]
    target: str | None = None
    expected: Any | None = None
    actual: Any | None = None
    reason: str
    repair_hint: str | None = None


class PlanEvaluationResult(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    is_acceptable: bool
    hard_failures: list[PlanFailure] = Field(default_factory=list)
    soft_failures: list[PlanFailure] = Field(default_factory=list)
    summary: str

