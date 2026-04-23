from datetime import UTC, datetime

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.db.serializers import serialize_many
from app.schemas.diary import DiaryCreate, DiaryGenerateRequest
from app.services.trip_service import ensure_trip_ownership


async def generate_diary(payload: DiaryGenerateRequest) -> dict:
    if settings.llm_diary_api_url:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(settings.llm_diary_api_url, json=payload.model_dump(mode="json"))
            response.raise_for_status()
            return response.json()

    emotions = ", ".join(payload.emotion_tags) if payload.emotion_tags else "설렘"
    place = payload.place or "파리의 어느 골목"
    note = payload.notes or "사진 속 순간들이 오래 남았다."
    return {
        "title": f"{place}에서 남긴 {emotions}의 하루",
        "generated_diary_text": (
            f"{payload.entry_date}의 파리는 조금 더 부드럽게 기억된다. "
            f"{place}에서 느낀 {emotions}의 감정이 사진 사이사이에 남아 있었고, "
            f"{note} 여행의 속도를 잠시 늦추니 작은 빛과 바람까지 하루의 문장이 되었다."
        ),
        "mood_keywords": payload.emotion_tags or ["romantic", "calm", "paris"],
    }


async def create_diary_entry(
    db: AsyncIOMotorDatabase,
    user_id: str,
    trip_id: str,
    payload: DiaryCreate,
) -> dict:
    await ensure_trip_ownership(db, user_id, trip_id)
    now = datetime.now(UTC)
    doc = payload.model_dump(mode="json")
    doc |= {"user_id": user_id, "trip_id": trip_id, "created_at": now, "updated_at": now}
    result = await db.diary_entry.insert_one(doc)
    created = await db.diary_entry.find_one({"_id": result.inserted_id})
    from app.db.serializers import serialize_doc

    return serialize_doc(created)


async def list_diary_entries(db: AsyncIOMotorDatabase, user_id: str, trip_id: str) -> list[dict]:
    await ensure_trip_ownership(db, user_id, trip_id)
    docs = await db.diary_entry.find({"trip_id": trip_id, "user_id": user_id}).sort("entry_date", -1).to_list(length=100)
    return serialize_many(docs)
