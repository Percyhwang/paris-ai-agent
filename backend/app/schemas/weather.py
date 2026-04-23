from datetime import date

from pydantic import BaseModel


class WeatherDay(BaseModel):
    date: date | str
    condition: str
    icon: str
    temp_min_c: float
    temp_max_c: float
    precipitation_chance: int
    travel_tip: str


class WeatherForecast(BaseModel):
    city: str = "Paris"
    country: str = "France"
    timezone: str = "Europe/Paris"
    days: list[WeatherDay]
