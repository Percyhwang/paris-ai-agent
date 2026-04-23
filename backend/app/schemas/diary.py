from datetime import date, datetime

from pydantic import BaseModel, Field


class DiaryBase(BaseModel):
    entry_date: date
    photo_urls: list[str] = Field(default_factory=list)
    emotion_tags: list[str] = Field(default_factory=list)
    notes: str = ""
    place: str | None = None


class DiaryGenerateRequest(DiaryBase):
    pass


class DiaryCreate(DiaryBase):
    title: str | None = None
    generated_diary_text: str | None = None
    mood_keywords: list[str] = Field(default_factory=list)


class DiaryResponse(DiaryCreate):
    id: str
    user_id: str
    trip_id: str
    created_at: datetime | str
    updated_at: datetime | str


class DiaryGenerated(BaseModel):
    title: str
    generated_diary_text: str
    mood_keywords: list[str]
