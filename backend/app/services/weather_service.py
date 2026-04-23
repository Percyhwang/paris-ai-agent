from datetime import date, timedelta

import httpx
from fastapi import HTTPException

from app.core.config import settings


async def get_paris_forecast(days: int = 7) -> dict:
    if settings.weather_api_url:
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                response = await client.get(settings.weather_api_url, params={"city": "Paris", "days": days})
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=502, detail="Weather API failed") from exc

    today = date.today()
    conditions = [
        ("맑음", "☀️", 9, 18, 5, "세느 강변 산책과 야외 사진 촬영에 좋아요."),
        ("구름 조금", "🌤️", 10, 17, 15, "얇은 겉옷을 챙기면 골목 산책이 편해요."),
        ("흐림", "☁️", 8, 15, 30, "박물관 중심 일정으로 잡으면 안정적이에요."),
        ("가벼운 비", "🌦️", 7, 13, 55, "우산과 방수 신발을 챙기고 실내 명소를 섞어보세요."),
        ("맑음", "☀️", 11, 19, 10, "에펠탑 야경과 정원 피크닉 모두 추천해요."),
        ("구름 많음", "☁️", 9, 16, 25, "카페와 쇼핑 동선을 넣기 좋은 날이에요."),
        ("비", "🌧️", 6, 12, 70, "루브르나 오르세처럼 긴 실내 관람을 추천해요."),
    ]
    forecast = []
    for index in range(days):
        condition, icon, low, high, rain, tip = conditions[index % len(conditions)]
        forecast.append(
            {
                "date": today + timedelta(days=index),
                "condition": condition,
                "icon": icon,
                "temp_min_c": low,
                "temp_max_c": high,
                "precipitation_chance": rain,
                "travel_tip": tip,
            }
        )
    return {"city": "Paris", "country": "France", "timezone": "Europe/Paris", "days": forecast}
