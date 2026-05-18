from datetime import UTC, date, datetime, time
import re
from typing import Any

from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.db.serializers import serialize_doc, serialize_many, to_object_id
from app.schemas.trips import ItineraryUpdate, TripCreate, TripUpdate
from app.services.memory_retrieval_service import update_feedback_memory
from app.services.trip_state_service import save_itinerary_state


def _now() -> datetime:
    return datetime.now(UTC)


def _date_to_datetime(value: date | datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    return datetime.combine(value, time.min, tzinfo=UTC)


async def ensure_trip_ownership(db: AsyncIOMotorDatabase, user_id: str, trip_id: str) -> dict:
    trip = await db.trip_plans.find_one({"_id": to_object_id(trip_id, "trip_id"), "user_id": user_id})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


async def get_trip_detail(db: AsyncIOMotorDatabase, user_id: str, trip_id: str, language: str = "ko") -> dict:
    trip = await ensure_trip_ownership(db, user_id, trip_id)
    days = await db.itinerary_day.find({"trip_id": str(trip["_id"])}).sort("day_number", 1).to_list(length=60)
    serialized = serialize_doc(trip)
    serialized["itinerary_days"] = serialize_many(days)
    return _localize_trip_response(serialized, language)


async def list_user_trips(db: AsyncIOMotorDatabase, user_id: str, language: str = "ko") -> list[dict]:
    docs = await db.trip_plans.find({"user_id": user_id}).sort("created_at", -1).to_list(length=100)
    trips = serialize_many(docs)
    for trip in trips:
        trip.setdefault("itinerary_days", [])
    return [_localize_trip_response(trip, language) for trip in trips]


async def create_trip(db: AsyncIOMotorDatabase, user_id: str, payload: TripCreate) -> dict:
    now = _now()
    doc = {
        "user_id": user_id,
        "trip_title": payload.trip_title,
        "prompt": None,
        "start_date": _date_to_datetime(payload.start_date),
        "end_date": _date_to_datetime(payload.end_date),
        "total_days": payload.total_days,
        "style_tags": payload.style_tags,
        "status": "draft",
        "route_summary": None,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.trip_plans.insert_one(doc)
    trip_id = str(result.inserted_id)
    await _create_default_budget(db, trip_id)
    await db.users.update_one({"_id": ObjectId(user_id)}, {"$addToSet": {"trips": trip_id}, "$set": {"updated_at": now}})
    return await get_trip_detail(db, user_id, trip_id)


async def create_generated_trip(db: AsyncIOMotorDatabase, user_id: str, payload: dict[str, Any]) -> dict:
    now = _now()
    trip_doc = payload["trip"] | {"user_id": user_id, "created_at": now, "updated_at": now}
    trip_doc["start_date"] = _date_to_datetime(trip_doc.get("start_date"))
    trip_doc["end_date"] = _date_to_datetime(trip_doc.get("end_date"))
    result = await db.trip_plans.insert_one(trip_doc)
    trip_id = str(result.inserted_id)

    day_docs = []
    for day in payload.get("itinerary_days", []):
        day_doc = dict(day)
        day_doc["trip_id"] = trip_id
        day_doc["user_id"] = user_id
        day_doc["date"] = _date_to_datetime(day_doc.get("date"))
        day_doc["created_at"] = now
        day_doc["updated_at"] = now
        day_docs.append(day_doc)
    if day_docs:
        await db.itinerary_day.insert_many(day_docs)

    budget = payload.get("budget") or {}
    await _upsert_budget_doc(
        db,
        trip_id,
        {
            "attraction_total": budget.get("attraction_total", 0),
            "hotel_total": budget.get("hotel_total", 0),
            "custom_expenses": budget.get("custom_expenses", []),
            "currency": budget.get("currency", "EUR"),
        },
    )
    await db.users.update_one({"_id": ObjectId(user_id)}, {"$addToSet": {"trips": trip_id}, "$set": {"updated_at": now}})
    await save_itinerary_state(
        db,
        user_id=user_id,
        trip_id=trip_id,
        trip=trip_doc | {"id": trip_id},
        itinerary_days=payload.get("itinerary_days") or day_docs,
    )
    await update_feedback_memory(
        db,
        user_id=user_id,
        trip_id=trip_id,
        prompt=str(trip_doc.get("prompt") or payload.get("prompt") or ""),
        planning_brief=payload.get("planning_brief") or trip_doc.get("planning_brief"),
        itinerary_days=payload.get("itinerary_days") or day_docs,
        agent_evaluation=payload.get("agent_evaluation") or trip_doc.get("agent_evaluation"),
        source="trip_generation",
    )
    return await get_trip_detail(db, user_id, trip_id)


async def update_trip(db: AsyncIOMotorDatabase, user_id: str, trip_id: str, payload: TripUpdate) -> dict:
    await ensure_trip_ownership(db, user_id, trip_id)
    update = payload.model_dump(exclude_unset=True)
    if "start_date" in update:
        update["start_date"] = _date_to_datetime(update["start_date"])
    if "end_date" in update:
        update["end_date"] = _date_to_datetime(update["end_date"])
    update["updated_at"] = _now()
    await db.trip_plans.update_one({"_id": ObjectId(trip_id)}, {"$set": update})
    return await get_trip_detail(db, user_id, trip_id)


async def delete_trip(db: AsyncIOMotorDatabase, user_id: str, trip_id: str) -> None:
    await ensure_trip_ownership(db, user_id, trip_id)
    await db.trip_plans.delete_one({"_id": ObjectId(trip_id)})
    await db.itinerary_day.delete_many({"trip_id": trip_id})
    await db.budget_summary.delete_one({"trip_id": trip_id})
    await db.reservation_summary.delete_many({"trip_id": trip_id})
    await db.diary_entry.delete_many({"trip_id": trip_id})
    await db.users.update_one({"_id": ObjectId(user_id)}, {"$pull": {"trips": trip_id}, "$set": {"updated_at": _now()}})


async def get_itinerary(db: AsyncIOMotorDatabase, user_id: str, trip_id: str, language: str = "ko") -> list[dict]:
    await ensure_trip_ownership(db, user_id, trip_id)
    days = await db.itinerary_day.find({"trip_id": trip_id}).sort("day_number", 1).to_list(length=60)
    localized = _localize_trip_response({"itinerary_days": serialize_many(days)}, language)
    return localized["itinerary_days"]


async def replace_itinerary(
    db: AsyncIOMotorDatabase,
    user_id: str,
    trip_id: str,
    payload: ItineraryUpdate,
) -> list[dict]:
    await ensure_trip_ownership(db, user_id, trip_id)
    now = _now()
    await db.itinerary_day.delete_many({"trip_id": trip_id})
    day_docs = []
    for day in payload.days:
        day_doc = day.model_dump(mode="json", exclude={"id"})
        day_doc["trip_id"] = trip_id
        day_doc["user_id"] = user_id
        day_doc["date"] = _date_to_datetime(day_doc.get("date"))
        day_doc["created_at"] = now
        day_doc["updated_at"] = now
        day_docs.append(day_doc)
    if day_docs:
        await db.itinerary_day.insert_many(day_docs)
    await db.trip_plans.update_one({"_id": ObjectId(trip_id)}, {"$set": {"updated_at": now}})
    return await get_itinerary(db, user_id, trip_id)


async def _create_default_budget(db: AsyncIOMotorDatabase, trip_id: str) -> None:
    await _upsert_budget_doc(
        db,
        trip_id,
        {"attraction_total": 0, "hotel_total": 0, "custom_expenses": [], "currency": "EUR"},
    )


async def _upsert_budget_doc(db: AsyncIOMotorDatabase, trip_id: str, payload: dict) -> dict:
    now = _now()
    expenses = payload.get("custom_expenses", [])
    grand_total = payload.get("attraction_total", 0) + payload.get("hotel_total", 0) + sum(
        item.get("amount", 0) for item in expenses
    )
    doc = {
        "trip_id": trip_id,
        "attraction_total": payload.get("attraction_total", 0),
        "hotel_total": payload.get("hotel_total", 0),
        "custom_expenses": expenses,
        "grand_total": grand_total,
        "currency": payload.get("currency", "EUR"),
        "last_updated": now,
    }
    return await db.budget_summary.find_one_and_update(
        {"trip_id": trip_id},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )


TRIP_TEXT_EN = {
    "대표 명소와 감성 산책을 균형 있게 섞은 파리 여행 초안입니다.": "A balanced Paris draft that blends signature sights with atmospheric walks.",
    "도보와 짧은 지하철 이동을 섞은 무리 없는 파리 동선입니다.": "A comfortable Paris route that mixes walking with short metro hops.",
    "클래식 파리 첫 만남": "Classic First Day in Paris",
    "감성 골목과 성당 산책": "Atmospheric Lanes and Cathedral Walks",
    "여유로운 정원과 쇼핑": "Gardens, Shopping, and a Slow Evening",
    "루브르 박물관 핵심 작품 감상": "See the Louvre highlights",
    "루브르 박물관": "Louvre Museum",
    "모나리자와 고대 조각 중심으로 무리 없는 관람을 시작합니다.": "Start with a focused visit around the Mona Lisa and ancient sculpture galleries.",
    "튈르리 근처 가벼운 점심": "Light lunch near the Tuileries",
    "튈르리 정원": "Tuileries Garden",
    "정원 주변 카페에서 여유롭게 쉬어갑니다.": "Pause at a nearby cafe and keep the pace easy.",
    "오르세 미술관과 세느 산책": "Orsay Museum and Seine walk",
    "오르세 미술관": "Orsay Museum",
    "인상주의 작품과 시계창 포토스팟을 함께 즐깁니다.": "Enjoy impressionist works and the clock-window photo spot before a river walk.",
    "에펠탑 야경": "Eiffel Tower night view",
    "에펠탑": "Eiffel Tower",
    "트로카데로에서 반짝이는 조명을 바라보며 하루를 마무리합니다.": "End the day at Trocadero with the tower lights and a relaxed evening view.",
    "노트르담 주변 시테섬 산책": "Stroll around Notre-Dame and Ile de la Cite",
    "노트르담 대성당": "Notre-Dame Cathedral",
    "성당 외관과 강변 서점을 천천히 둘러봅니다.": "Take in the cathedral exterior and riverside bookstalls at an unhurried pace.",
    "마레 지구 브런치": "Brunch in Le Marais",
    "마레 지구": "Le Marais",
    "편안한 골목 카페에서 브런치를 즐깁니다.": "Settle into a relaxed neighborhood cafe for brunch.",
    "몽마르트르 예술가 언덕": "Montmartre artists' hill",
    "몽마르트르": "Montmartre",
    "사크레쾨르와 라 메종 로즈 골목을 연결해 걷습니다.": "Connect Sacre-Coeur, side streets, and La Maison Rose into one scenic walk.",
    "언덕 아래 비스트로 저녁": "Bistro dinner below the hill",
    "아베스 광장": "Abbesses",
    "붐비는 중심가보다 조용한 비스트로를 추천합니다.": "Choose a quieter bistro away from the busiest center streets.",
    "뤽상부르 공원 휴식": "Rest in Luxembourg Garden",
    "뤽상부르 공원": "Luxembourg Garden",
    "초록 의자에 앉아 여행 템포를 낮춥니다.": "Sit in the green chairs and let the travel tempo slow down.",
    "생제르맹 점심": "Lunch in Saint-Germain",
    "생제르맹데프레": "Saint-Germain-des-Pres",
    "클래식한 카페 거리에서 점심을 잡습니다.": "Pick a classic cafe street for an easy lunch.",
    "봉마르셰와 근처 산책": "Le Bon Marche and nearby streets",
    "봉마르셰": "Le Bon Marche",
    "기념품과 식료품 쇼핑을 부담 없이 즐깁니다.": "Browse gifts and food-hall finds without overloading the day.",
    "세느 강변 노을": "Sunset by the Seine",
    "퐁데자르": "Pont des Arts",
    "해 질 무렵 강변을 따라 사진을 남깁니다.": "Take photos along the river as the evening light settles in.",
    "1시간": "1 hour",
    "2시간": "2 hours",
    "3시간": "3 hours",
    "1시간 30분": "1 hour 30 minutes",
}


def _localize_trip_response(trip: dict, language: str) -> dict:
    if language != "en":
        return trip

    localized = dict(trip)
    localized["trip_title"] = _localize_trip_title(localized.get("trip_title"))
    localized["route_summary"] = _localize_text(localized.get("route_summary"))

    days = []
    for day in localized.get("itinerary_days", []):
        localized_day = dict(day)
        localized_day["title"] = _localize_text(localized_day.get("title"))
        localized_day["route_summary"] = _localize_text(localized_day.get("route_summary"))
        localized_items = []
        for item in localized_day.get("items", []):
            localized_item = dict(item)
            localized_item["title"] = _localize_text(localized_item.get("title"))
            localized_item["description"] = _localize_text(localized_item.get("description"))
            localized_item["estimated_duration"] = _localize_text(localized_item.get("estimated_duration"))
            localized_item["role_label"] = _localize_text(localized_item.get("role_label"))
            localized_item["reasoning"] = _localize_text(localized_item.get("reasoning"))
            if isinstance(localized_item.get("place"), dict):
                place = dict(localized_item["place"])
                place["name"] = _localize_text(place.get("name"))
                localized_item["place"] = place
            localized_items.append(localized_item)
        localized_day["items"] = localized_items
        days.append(localized_day)
    localized["itinerary_days"] = days
    return localized


def _localize_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return TRIP_TEXT_EN.get(value, value)


def _localize_trip_title(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    museum_match = re.fullmatch(r"(\d+)일 파리 뮤지엄 여행", value)
    if museum_match:
        return f"{museum_match.group(1)}-Day Paris Museum Trip"

    night_match = re.fullmatch(r"(\d+)일 파리 야경 여행", value)
    if night_match:
        return f"{night_match.group(1)}-Day Paris Night-View Trip"

    mood_match = re.fullmatch(r"(\d+)일 파리 감성 여행", value)
    if mood_match:
        return f"{mood_match.group(1)}-Day Atmospheric Paris Trip"

    return _localize_text(value)
