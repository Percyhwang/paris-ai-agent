from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class UserPreferences(BaseModel):
    travel_style: list[str] = Field(default_factory=list)
    favorite_categories: list[str] = Field(default_factory=list)
    budget_currency: str = "EUR"
    language: str = "ko"


class UserResponse(BaseModel):
    id: str
    google_id: str
    email: EmailStr
    name: str
    profile_image: str | None = None
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    trips: list[str] = Field(default_factory=list)
    created_at: datetime | str
    updated_at: datetime | str


class UserUpdate(BaseModel):
    name: str | None = None
    profile_image: str | None = None
    preferences: UserPreferences | None = None


class GoogleProfile(BaseModel):
    google_id: str
    email: EmailStr
    name: str
    profile_image: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
