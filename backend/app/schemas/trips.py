from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.places import Coordinates


class TripGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=1000)
    start_date: date | None = None
    end_date: date | None = None
    total_days: int | None = Field(default=None, ge=1, le=30)
    style_tags: list[str] = Field(default_factory=list)


class TripCreate(BaseModel):
    trip_title: str
    start_date: date | None = None
    end_date: date | None = None
    total_days: int = Field(default=1, ge=1, le=30)
    style_tags: list[str] = Field(default_factory=list)


class TripUpdate(BaseModel):
    trip_title: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    style_tags: list[str] | None = None


class ItineraryPlace(BaseModel):
    place_id: str | None = None
    name: str
    coordinates: Coordinates | None = None
    category: str | None = None


class ItineraryItem(BaseModel):
    id: str | None = None
    time_slot: Literal["morning", "lunch", "afternoon", "evening"]
    start_time: str
    title: str
    place: ItineraryPlace
    description: str
    estimated_duration: str


class ItineraryDay(BaseModel):
    id: str | None = None
    day_number: int
    date: date | str | None = None
    title: str
    items: list[ItineraryItem] = Field(default_factory=list)
    route_summary: str | None = None


class ItineraryUpdate(BaseModel):
    days: list[ItineraryDay]


class TripResponse(BaseModel):
    id: str
    user_id: str
    trip_title: str
    prompt: str | None = None
    start_date: date | datetime | str | None = None
    end_date: date | datetime | str | None = None
    total_days: int
    style_tags: list[str] = Field(default_factory=list)
    status: str = "draft"
    itinerary_days: list[ItineraryDay] = Field(default_factory=list)
    route_summary: str | None = None
    created_at: datetime | str
    updated_at: datetime | str
