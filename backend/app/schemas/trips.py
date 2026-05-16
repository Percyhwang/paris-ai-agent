from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.places import Coordinates


class TripGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=1000)
    start_date: date | None = None
    end_date: date | None = None
    total_days: int | None = Field(default=None, ge=1, le=30)
    style_tags: list[str] = Field(default_factory=list)


class TripAgentModifyRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=1000)
    target_day: int | None = Field(default=None, ge=1, le=30)


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
    cuisine: list[str] | str | None = None
    admission_fee: str | None = None
    admission_fee_amount: float | None = None
    rating: float | None = None
    review_count: int | None = None
    google_place_id: str | None = None
    google_maps_uri: str | None = None


class RouteStep(BaseModel):
    instruction: str
    travel_mode: str | None = None
    line_name: str | None = None
    line_short_name: str | None = None
    vehicle_type: str | None = None
    departure_stop: str | None = None
    arrival_stop: str | None = None
    duration_text: str | None = None
    stop_count: int | None = None


class RouteLeg(BaseModel):
    mode: str
    summary: str
    distance_meters: int | None = None
    duration_seconds: int | None = None
    duration_text: str
    buffer_minutes: int | None = None
    rawDurationMinutes: int | None = None
    bufferMinutes: int | None = None
    totalTransferMinutes: int | None = None
    scheduled_duration_seconds: int | None = None
    scheduled_duration_text: str | None = None
    compact_summary: str | None = None
    comfort_summary: str | None = None
    effort_level: Literal["low", "medium", "high"] | None = None
    restBufferReason: str | None = None
    steps: list[RouteStep] = Field(default_factory=list)
    transit_lines: list[str] = Field(default_factory=list)
    fallback: bool = False


class ItineraryItem(BaseModel):
    id: str | None = None
    time_slot: Literal["morning", "lunch", "afternoon", "evening"]
    start_time: str
    end_time: str | None = None
    itemKind: Literal["stop", "gap"] | None = None
    title: str
    place: ItineraryPlace
    description: str
    estimated_duration: str
    duration_minutes: int | None = None
    role_label: str | None = None
    role_icon: str | None = None
    reasoning: str | None = None
    slotPurpose: str | None = None
    userPreferenceReason: str | None = None
    timeReason: str | None = None
    restBufferReason: str | None = None
    isNightViewSpot: bool | None = None
    expectedExperience: str | None = None
    editableReason: str | None = None
    gapReason: str | None = None
    nearbyMealNeeded: bool | None = None
    energy_level: int | None = Field(default=None, ge=1, le=5)
    route_to_next: RouteLeg | None = None


class ItineraryDay(BaseModel):
    id: str | None = None
    day_number: int
    date: date | str | None = None
    title: str
    theme: str | None = None
    dayTheme: str | None = None
    daySummary: str | None = None
    routeSummary: str | None = None
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
    planning_brief: dict[str, Any] | None = None
    constraint_validation: dict[str, Any] | None = None
    itinerary_days: list[ItineraryDay] = Field(default_factory=list)
    route_summary: str | None = None
    created_at: datetime | str
    updated_at: datetime | str
