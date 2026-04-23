from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class BudgetItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    category: Literal["attraction", "hotel", "custom", "other"]
    title: str
    amount: float = Field(ge=0)
    currency: str = "EUR"
    day_number: int | None = None
    note: str | None = None


class BudgetSummary(BaseModel):
    id: str | None = None
    trip_id: str
    attraction_total: float = 0
    hotel_total: float = 0
    custom_expenses: list[BudgetItem] = Field(default_factory=list)
    grand_total: float = 0
    currency: str = "EUR"
    last_updated: datetime | str | None = None


class BudgetUpdate(BaseModel):
    attraction_total: float | None = Field(default=None, ge=0)
    hotel_total: float | None = Field(default=None, ge=0)
    custom_expenses: list[BudgetItem] | None = None
    currency: str | None = None


class BudgetItemCreate(BaseModel):
    category: Literal["attraction", "hotel", "custom", "other"] = "custom"
    title: str
    amount: float = Field(ge=0)
    currency: str = "EUR"
    day_number: int | None = None
    note: str | None = None
