from datetime import UTC, date, datetime, time
from typing import Any

from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.db.serializers import serialize_doc, serialize_many, to_object_id
from app.schemas.trips import ItineraryUpdate, TripCreate, TripUpdate


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


async def get_trip_detail(db: AsyncIOMotorDatabase, user_id: str, trip_id: str) -> dict:
    trip = await ensure_trip_ownership(db, user_id, trip_id)
    days = await db.itinerary_day.find({"trip_id": str(trip["_id"])}).sort("day_number", 1).to_list(length=60)
    serialized = serialize_doc(trip)
    serialized["itinerary_days"] = serialize_many(days)
    return serialized


async def list_user_trips(db: AsyncIOMotorDatabase, user_id: str) -> list[dict]:
    docs = await db.trip_plans.find({"user_id": user_id}).sort("created_at", -1).to_list(length=100)
    trips = serialize_many(docs)
    for trip in trips:
        trip.setdefault("itinerary_days", [])
    return trips


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


async def get_itinerary(db: AsyncIOMotorDatabase, user_id: str, trip_id: str) -> list[dict]:
    await ensure_trip_ownership(db, user_id, trip_id)
    days = await db.itinerary_day.find({"trip_id": trip_id}).sort("day_number", 1).to_list(length=60)
    return serialize_many(days)


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
