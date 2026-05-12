from fastapi import APIRouter, Query, Request

from app.core.i18n import normalize_language
from app.core.responses import api_ok
from app.db.mongodb import get_optional_database
from app.services.weather_service import get_paris_forecast

router = APIRouter()


@router.get("/paris")
async def get_paris_weather(
    request: Request,
) -> dict:
    language = normalize_language(request.headers.get("accept-language"))
    db = get_optional_database()
    forecast = await get_paris_forecast(db=db, days=1, language=language)
    return api_ok(forecast["days"][0] | {"city": forecast["city"]})


@router.get("/paris/forecast")
async def get_paris_forecast_route(
    request: Request,
    days: int = Query(default=7, ge=1, le=14),
) -> dict:
    language = normalize_language(request.headers.get("accept-language"))
    db = get_optional_database()
    return api_ok(await get_paris_forecast(db=db, days=days, language=language))
