from fastapi import APIRouter, Query

from app.core.responses import api_ok
from app.services.weather_service import get_paris_forecast

router = APIRouter()


@router.get("/paris")
async def get_paris_weather() -> dict:
    forecast = await get_paris_forecast(days=1)
    return api_ok(forecast["days"][0] | {"city": "Paris"})


@router.get("/paris/forecast")
async def get_paris_forecast_route(days: int = Query(default=7, ge=1, le=14)) -> dict:
    return api_ok(await get_paris_forecast(days=days))
