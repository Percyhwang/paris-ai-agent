from pydantic import BaseModel, Field


class Coordinates(BaseModel):
    lat: float
    lng: float


class PlaceResponse(BaseModel):
    id: str | None = None
    slug: str
    name: str
    category: str
    coordinates: Coordinates
    image_url: str
    short_description: str
    full_description: str
    history: str
    photo_spot_tips: list[str] = Field(default_factory=list)
    estimated_visit_duration: str
    admission_fee: str | None = None
    location: str
    tags: list[str] = Field(default_factory=list)
    popularity: int = 0
