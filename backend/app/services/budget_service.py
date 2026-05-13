from datetime import UTC, date, datetime

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.db.serializers import serialize_doc
from app.schemas.budget import BudgetItem, BudgetItemCreate, BudgetUpdate
from app.services.trip_service import ensure_trip_ownership

ADMISSION_FEE_BY_SLUG: dict[str, float] = {
    "eiffel-tower": 36.7,
    "louvre-museum": 32,
    "musee-dorsay": 16,
    "arc-de-triomphe": 22,
    "sainte-chapelle": 22,
    "palais-garnier": 25,
}

ADMISSION_FEE_BY_NAME: dict[str, float] = {
    "eiffel tower": 36.7,
    "tour eiffel": 36.7,
    "louvre museum": 32,
    "louvre": 32,
    "musee d'orsay": 16,
    "orsay museum": 16,
    "arc de triomphe": 22,
    "sainte-chapelle": 22,
    "palais garnier": 25,
}


def _recalculate(doc: dict) -> dict:
    expenses = doc.get("custom_expenses", [])
    doc["grand_total"] = doc.get("attraction_total", 0) + doc.get("hotel_total", 0) + sum(
        item.get("amount", 0) for item in expenses
    )
    doc["last_updated"] = datetime.now(UTC)
    return doc


async def get_budget(db: AsyncIOMotorDatabase, user_id: str, trip_id: str) -> dict:
    await ensure_trip_ownership(db, user_id, trip_id)
    attraction_total = await _calculate_itinerary_admission_total(db, trip_id)
    doc = await db.budget_summary.find_one({"trip_id": trip_id})
    if not doc:
        doc = await db.budget_summary.find_one_and_update(
            {"trip_id": trip_id},
            {
                "$set": _recalculate(
                    {
                        "trip_id": trip_id,
                        "attraction_total": attraction_total,
                        "hotel_total": 0,
                        "custom_expenses": [],
                        "currency": "EUR",
                    }
                )
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    elif doc.get("attraction_total") != attraction_total:
        update_doc = dict(doc)
        update_doc.pop("_id", None)
        update_doc["attraction_total"] = attraction_total
        doc = await db.budget_summary.find_one_and_update(
            {"trip_id": trip_id},
            {"$set": _recalculate(update_doc)},
            return_document=ReturnDocument.AFTER,
        )
    return serialize_doc(doc)


async def _calculate_itinerary_admission_total(db: AsyncIOMotorDatabase, trip_id: str) -> float:
    days = await db.itinerary_day.find({"trip_id": trip_id}).to_list(length=60)
    seen: set[str] = set()
    total = 0.0
    for day in days:
        for item in day.get("items") or []:
            place = item.get("place") or {}
            key = str(place.get("place_id") or place.get("name") or item.get("title") or "").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            total += _admission_fee_for_place(place, item, day)
    return round(total, 2)


def _admission_fee_for_place(place: dict, item: dict, day: dict | None = None) -> float:
    place_id = str(place.get("place_id") or "").lower()
    if place_id == "arc-de-triomphe":
        return _arc_de_triomphe_fee(day.get("date") if day else None)
    if place_id in ADMISSION_FEE_BY_SLUG:
        return ADMISSION_FEE_BY_SLUG[place_id]

    amount = place.get("admission_fee_amount") or item.get("admission_fee_amount")
    if isinstance(amount, (int, float)):
        return float(amount)

    name = str(place.get("name") or item.get("title") or "").lower()
    normalized = "".join(char if char.isalnum() else " " for char in name)
    normalized = " ".join(normalized.split())
    for known_name, fee in ADMISSION_FEE_BY_NAME.items():
        if known_name in normalized or normalized in known_name:
            if known_name == "arc de triomphe":
                return _arc_de_triomphe_fee(day.get("date") if day else None)
            return fee
    return 0.0


def _arc_de_triomphe_fee(raw_date: object) -> float:
    visit_date = _parse_visit_date(raw_date)
    if visit_date is None:
        return 22.0
    if 4 <= visit_date.month <= 9:
        return 16.0 if visit_date.weekday() == 2 else 22.0
    return 16.0


def _parse_visit_date(raw_date: object) -> date | None:
    if isinstance(raw_date, datetime):
        return raw_date.date()
    if isinstance(raw_date, date):
        return raw_date
    if isinstance(raw_date, str) and raw_date:
        try:
            return datetime.fromisoformat(raw_date.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


async def update_budget(db: AsyncIOMotorDatabase, user_id: str, trip_id: str, payload: BudgetUpdate) -> dict:
    current = await get_budget(db, user_id, trip_id)
    merged = current | payload.model_dump(exclude_unset=True, mode="json")
    merged.pop("id", None)
    merged = _recalculate(merged)
    doc = await db.budget_summary.find_one_and_update(
        {"trip_id": trip_id},
        {"$set": merged},
        return_document=ReturnDocument.AFTER,
    )
    return serialize_doc(doc)


async def add_budget_item(db: AsyncIOMotorDatabase, user_id: str, trip_id: str, payload: BudgetItemCreate) -> dict:
    current = await get_budget(db, user_id, trip_id)
    item = BudgetItem(**payload.model_dump()).model_dump(mode="json")
    expenses = current.get("custom_expenses", []) + [item]
    return await update_budget(db, user_id, trip_id, BudgetUpdate(custom_expenses=expenses))


async def delete_budget_item(db: AsyncIOMotorDatabase, user_id: str, trip_id: str, item_id: str) -> dict:
    current = await get_budget(db, user_id, trip_id)
    expenses = [item for item in current.get("custom_expenses", []) if item.get("id") != item_id]
    if len(expenses) == len(current.get("custom_expenses", [])):
        raise HTTPException(status_code=404, detail="Budget item not found")
    return await update_budget(db, user_id, trip_id, BudgetUpdate(custom_expenses=expenses))
