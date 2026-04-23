from datetime import date, timedelta
from uuid import uuid4

import httpx
from fastapi import HTTPException

from app.core.config import settings
from app.schemas.trips import TripGenerateRequest


async def generate_trip_payload(request: TripGenerateRequest) -> dict:
    if settings.external_agent_api_url:
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.post(settings.external_agent_api_url, json=request.model_dump(mode="json"))
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=502, detail="External agent API failed") from exc

    return _mock_trip_payload(request)


def _mock_trip_payload(request: TripGenerateRequest) -> dict:
    total_days = request.total_days or _infer_days(request.prompt) or 3
    start = request.start_date or (date.today() + timedelta(days=45))
    end = request.end_date or (start + timedelta(days=total_days - 1))
    tags = request.style_tags or _infer_tags(request.prompt)

    templates = [
        (
            "클래식 파리 첫 만남",
            [
                ("morning", "09:30", "루브르 박물관 핵심 작품 감상", "루브르 박물관", "museum", 48.8606, 2.3376, "모나리자와 고대 조각 중심으로 무리 없는 관람을 시작합니다.", "3시간"),
                ("lunch", "12:40", "튈르리 근처 가벼운 점심", "튈르리 정원", "park", 48.8635, 2.327, "정원 주변 카페에서 여유롭게 쉬어갑니다.", "1시간"),
                ("afternoon", "15:00", "오르세 미술관과 세느 산책", "오르세 미술관", "museum", 48.86, 2.3266, "인상주의 작품과 시계창 포토스팟을 함께 즐깁니다.", "2시간"),
                ("evening", "20:00", "에펠탑 야경", "에펠탑", "landmark", 48.8584, 2.2945, "트로카데로에서 반짝이는 조명을 바라보며 하루를 마무리합니다.", "1시간 30분"),
            ],
        ),
        (
            "감성 골목과 성당 산책",
            [
                ("morning", "10:00", "노트르담 주변 시테섬 산책", "노트르담 대성당", "cathedral", 48.853, 2.3499, "성당 외관과 강변 서점을 천천히 둘러봅니다.", "2시간"),
                ("lunch", "12:30", "마레 지구 브런치", "마레 지구", "neighborhood", 48.8575, 2.358, "편안한 골목 카페에서 브런치를 즐깁니다.", "1시간"),
                ("afternoon", "15:00", "몽마르트르 예술가 언덕", "몽마르트르", "neighborhood", 48.8867, 2.3431, "사크레쾨르와 라 메종 로즈 골목을 연결해 걷습니다.", "3시간"),
                ("evening", "19:30", "언덕 아래 비스트로 저녁", "아베스 광장", "neighborhood", 48.8844, 2.3386, "붐비는 중심가보다 조용한 비스트로를 추천합니다.", "1시간 30분"),
            ],
        ),
        (
            "여유로운 정원과 쇼핑",
            [
                ("morning", "10:00", "뤽상부르 공원 휴식", "뤽상부르 공원", "park", 48.8462, 2.3372, "초록 의자에 앉아 여행 템포를 낮춥니다.", "1시간 30분"),
                ("lunch", "12:00", "생제르맹 점심", "생제르맹데프레", "neighborhood", 48.8539, 2.3331, "클래식한 카페 거리에서 점심을 잡습니다.", "1시간"),
                ("afternoon", "14:30", "봉마르셰와 근처 산책", "봉마르셰", "shopping", 48.8512, 2.3256, "기념품과 식료품 쇼핑을 부담 없이 즐깁니다.", "2시간"),
                ("evening", "18:30", "세느 강변 노을", "퐁데자르", "landmark", 48.8583, 2.3375, "해 질 무렵 강변을 따라 사진을 남깁니다.", "1시간"),
            ],
        ),
    ]

    itinerary_days = []
    for index in range(total_days):
        title, items = templates[index % len(templates)]
        itinerary_days.append(
            {
                "day_number": index + 1,
                "date": start + timedelta(days=index),
                "title": title,
                "route_summary": "도보와 짧은 지하철 이동을 섞은 무리 없는 파리 동선입니다.",
                "items": [
                    {
                        "id": str(uuid4()),
                        "time_slot": slot,
                        "start_time": start_time,
                        "title": item_title,
                        "place": {
                            "name": place_name,
                            "category": category,
                            "coordinates": {"lat": lat, "lng": lng},
                        },
                        "description": description,
                        "estimated_duration": duration,
                    }
                    for slot, start_time, item_title, place_name, category, lat, lng, description, duration in items
                ],
            }
        )

    return {
        "trip": {
            "trip_title": _title_from_prompt(request.prompt, total_days),
            "prompt": request.prompt,
            "start_date": start,
            "end_date": end,
            "total_days": total_days,
            "style_tags": tags,
            "status": "generated",
            "route_summary": "대표 명소와 감성 산책을 균형 있게 섞은 파리 여행 초안입니다.",
        },
        "itinerary_days": itinerary_days,
        "budget": {
            "attraction_total": 22 * total_days,
            "hotel_total": 180 * total_days,
            "custom_expenses": [],
            "currency": "EUR",
        },
    }


def _infer_days(prompt: str) -> int | None:
    for days in range(1, 15):
        if f"{days}박" in prompt:
            return days + 1
        if f"{days}일" in prompt:
            return days
    return None


def _infer_tags(prompt: str) -> list[str]:
    tags = []
    keyword_map = {
        "박물관": "museum",
        "조용": "calm",
        "야경": "night-view",
        "감성": "romantic",
        "가족": "family",
        "쇼핑": "shopping",
    }
    for keyword, tag in keyword_map.items():
        if keyword in prompt:
            tags.append(tag)
    return tags or ["classic", "balanced"]


def _title_from_prompt(prompt: str, total_days: int) -> str:
    if "박물관" in prompt:
        return f"{total_days}일 파리 뮤지엄 여행"
    if "야경" in prompt:
        return f"{total_days}일 파리 야경 여행"
    return f"{total_days}일 파리 감성 여행"
