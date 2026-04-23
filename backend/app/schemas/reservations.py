from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ReservationCreate(BaseModel):
    reservation_type: Literal["hotel", "flight", "ticket", "activity"]
    provider: str
    title: str
    start_date: date | None = None
    end_date: date | None = None
    price: float = Field(default=0, ge=0)
    currency: str = "EUR"
    status: Literal["pending", "confirmed", "canceled"] = "pending"
    booking_reference: str | None = None


class ReservationResponse(ReservationCreate):
    id: str
    trip_id: str
    user_id: str
    created_at: datetime | str
    updated_at: datetime | str
