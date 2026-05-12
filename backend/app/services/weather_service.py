from datetime import UTC, datetime, timedelta

import httpx
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
PARIS_CITY = "Paris"
PARIS_COUNTRY = "France"
PARIS_TIMEZONE = "Europe/Paris"
PARIS_LATITUDE = 48.8566
PARIS_LONGITUDE = 2.3522

WEATHER_LABELS = {
    0: ("맑음", "Clear"),
    1: ("대체로 맑음", "Mostly clear"),
    2: ("구름 조금", "Partly cloudy"),
    3: ("흐림", "Cloudy"),
    45: ("안개", "Foggy"),
    48: ("안개", "Foggy"),
    51: ("이슬비", "Light drizzle"),
    53: ("이슬비", "Drizzle"),
    55: ("이슬비", "Heavy drizzle"),
    56: ("어는 이슬비", "Freezing drizzle"),
    57: ("어는 이슬비", "Freezing drizzle"),
    61: ("비", "Rain"),
    63: ("비", "Rain"),
    65: ("비", "Heavy rain"),
    66: ("비", "Freezing rain"),
    67: ("비", "Freezing rain"),
    71: ("눈", "Snow"),
    73: ("눈", "Snow"),
    75: ("눈", "Heavy snow"),
    77: ("눈", "Snow grains"),
    80: ("소나기", "Showers"),
    81: ("소나기", "Showers"),
    82: ("소나기", "Heavy showers"),
    85: ("눈", "Snow showers"),
    86: ("눈", "Snow showers"),
    95: ("뇌우", "Thunderstorm"),
    96: ("뇌우", "Thunderstorm"),
    99: ("뇌우", "Thunderstorm"),
}

WEATHER_ICONS = {
    0: "☀️",
    1: "🌤️",
    2: "⛅",
    3: "☁️",
    45: "🌫️",
    48: "🌫️",
    51: "🌦️",
    53: "🌦️",
    55: "🌦️",
    56: "🥶",
    57: "🥶",
    61: "🌧️",
    63: "🌧️",
    65: "🌧️",
    66: "🌧️",
    67: "🌧️",
    71: "❄️",
    73: "❄️",
    75: "❄️",
    77: "❄️",
    80: "🌦️",
    81: "🌦️",
    82: "🌦️",
    85: "❄️",
    86: "❄️",
    95: "⛈️",
    96: "⛈️",
    99: "⛈️",
}


async def get_paris_forecast(
    db: AsyncIOMotorDatabase | None,
    days: int = 7,
    language: str = "ko",
) -> dict:
    cache_key = f"paris_forecast:{language}:{days}"
    cached = await _get_cached_forecast(db, cache_key)
    if cached:
        return cached

    payload = await _fetch_open_meteo_forecast(days=days)
    forecast = _normalize_forecast(payload, days=days, language=language)
    await _store_forecast_cache(db, cache_key=cache_key, payload=forecast)
    return forecast


async def _fetch_open_meteo_forecast(days: int) -> dict:
    weather_api_url = settings.weather_api_url or OPEN_METEO_FORECAST_URL
    params = {
        "latitude": PARIS_LATITUDE,
        "longitude": PARIS_LONGITUDE,
        "timezone": PARIS_TIMEZONE,
        "forecast_days": days,
        "daily": ",".join(
            [
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_probability_max",
            ]
        ),
    }

    async with httpx.AsyncClient(timeout=20) as client:
        try:
            response = await client.get(weather_api_url, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Weather API failed") from exc

    payload = response.json()
    if "daily" not in payload:
        raise HTTPException(status_code=502, detail="Weather API returned an unexpected response")
    return payload


def _normalize_forecast(payload: dict, days: int, language: str) -> dict:
    daily = payload.get("daily") or {}
    dates = daily.get("time") or []
    weather_codes = daily.get("weather_code") or []
    max_temps = daily.get("temperature_2m_max") or []
    min_temps = daily.get("temperature_2m_min") or []
    precipitation_probs = daily.get("precipitation_probability_max") or []

    if not dates:
        raise HTTPException(status_code=502, detail="Weather API returned no forecast data")

    forecast_days = []
    for date_value, weather_code, max_temp, min_temp, precipitation in zip(
        dates,
        weather_codes,
        max_temps,
        min_temps,
        precipitation_probs,
        strict=False,
    ):
        weather_code_int = int(weather_code or 0)
        condition, icon = _map_weather_code(weather_code_int, language)
        precipitation_chance = int(round(float(precipitation or 0)))
        temp_min_c = round(float(min_temp or 0), 1)
        temp_max_c = round(float(max_temp or 0), 1)
        forecast_days.append(
            {
                "date": date_value,
                "condition": condition,
                "icon": icon,
                "temp_min_c": temp_min_c,
                "temp_max_c": temp_max_c,
                "precipitation_chance": precipitation_chance,
                "travel_tip": _build_travel_tip(
                    weather_code=weather_code_int,
                    precipitation_chance=precipitation_chance,
                    temp_min_c=temp_min_c,
                    temp_max_c=temp_max_c,
                    language=language,
                ),
            }
        )

    return {
        "city": PARIS_CITY,
        "country": PARIS_COUNTRY,
        "timezone": payload.get("timezone") or PARIS_TIMEZONE,
        "days": forecast_days[:days],
    }


def _map_weather_code(weather_code: int, language: str) -> tuple[str, str]:
    ko_label, en_label = WEATHER_LABELS.get(weather_code, ("변화가 많은 날씨", "Mixed weather"))
    label = en_label if language == "en" else ko_label
    return label, WEATHER_ICONS.get(weather_code, "🌍")


def _build_travel_tip(
    weather_code: int,
    precipitation_chance: int,
    temp_min_c: float,
    temp_max_c: float,
    language: str,
) -> str:
    if language == "en":
        if weather_code in {95, 96, 99}:
            return "Thunder is possible, so museums or cafes may work better than long outdoor blocks."
        if weather_code in {71, 73, 75, 77, 85, 86}:
            return "Paths may be slippery, so wear shoes with grip and leave a bit more time between stops."
        if precipitation_chance >= 70 or weather_code in {61, 63, 65, 66, 67, 80, 81, 82}:
            return "Bring an umbrella or light waterproof layer and mix indoor stops into your route."
        if weather_code in {45, 48}:
            return "Fog can limit views, so indoor spots and neighborhood walks may work better than scenic lookouts."
        if temp_max_c >= 27:
            return "The afternoon can feel warm, so carry water and shift outdoor highlights to the morning or late afternoon."
        if temp_min_c <= 7:
            return "Mornings and evenings may feel chilly, so a light coat or knit layer will help."
        if weather_code in {0, 1, 2} and precipitation_chance <= 20:
            return "A good day for outdoor walks and viewpoints, especially with a park or riverside stop."
        return "Comfortable weather for a balanced day that mixes indoor attractions with outdoor strolling."

    if weather_code in {95, 96, 99}:
        return "천둥 가능성이 있어 야외 장시간 일정보다는 박물관이나 카페 중심으로 움직이는 편이 좋아요."
    if weather_code in {71, 73, 75, 77, 85, 86}:
        return "길이 미끄러울 수 있으니 미끄럼 방지 신발을 챙기고, 이동 간격을 조금 여유 있게 잡아두세요."
    if precipitation_chance >= 70 or weather_code in {61, 63, 65, 66, 67, 80, 81, 82}:
        return "비에 대비해 우산이나 가벼운 방수 아우터를 챙기면 좋아요. 실내 명소를 함께 섞으면 일정이 편해져요."
    if weather_code in {45, 48}:
        return "안개로 시야가 흐릴 수 있어 전망 포인트보다 실내 공간이나 골목 산책 위주 일정이 잘 어울려요."
    if temp_max_c >= 27:
        return "한낮에는 햇볕이 강할 수 있어 물과 선글라스를 챙기고, 야외 일정은 오전이나 늦은 오후가 더 좋아요."
    if temp_min_c <= 7:
        return "아침저녁으로 꽤 서늘할 수 있어 가벼운 코트나 니트 겉옷을 챙겨두면 편해요."
    if weather_code in {0, 1, 2} and precipitation_chance <= 20:
        return "야외 산책과 전망 명소를 넣기 좋은 날이에요. 공원이나 강변 코스를 함께 잡아보세요."
    return "걷기 좋은 날씨예요. 실내 명소와 야외 산책 코스를 균형 있게 섞으면 편안하게 즐길 수 있어요."


async def _get_cached_forecast(db: AsyncIOMotorDatabase | None, cache_key: str) -> dict | None:
    if db is None:
        return None
    now = datetime.now(UTC)
    cached = await db.weather_cache.find_one({"cache_key": cache_key, "expires_at": {"$gt": now}})
    return cached.get("payload") if cached else None


async def _store_forecast_cache(
    db: AsyncIOMotorDatabase | None,
    cache_key: str,
    payload: dict,
) -> None:
    if db is None:
        return
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.weather_cache_ttl_minutes)
    await db.weather_cache.update_one(
        {"cache_key": cache_key},
        {
            "$set": {
                "cache_key": cache_key,
                "payload": payload,
                "updated_at": now,
                "expires_at": expires_at,
            }
        },
        upsert=True,
    )
