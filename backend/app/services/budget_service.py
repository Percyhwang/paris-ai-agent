from datetime import UTC, datetime

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.db.serializers import serialize_doc
from app.schemas.budget import BudgetItem, BudgetItemCreate, BudgetUpdate
from app.services.trip_service import ensure_trip_ownership


def _recalculate(doc: dict) -> dict:
    expenses = doc.get("custom_expenses", [])
    doc["grand_total"] = doc.get("attraction_total", 0) + doc.get("hotel_total", 0) + sum(
        item.get("amount", 0) for item in expenses
    )
    doc["last_updated"] = datetime.now(UTC)
    return doc


async def get_budget(db: AsyncIOMotorDatabase, user_id: str, trip_id: str) -> dict:
    await ensure_trip_ownership(db, user_id, trip_id)
    doc = await db.budget_summary.find_one({"trip_id": trip_id})
    if not doc:
        doc = await db.budget_summary.find_one_and_update(
            {"trip_id": trip_id},
            {
                "$set": _recalculate(
                    {
                        "trip_id": trip_id,
                        "attraction_total": 0,
                        "hotel_total": 0,
                        "custom_expenses": [],
                        "currency": "EUR",
                    }
                )
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    return serialize_doc(doc)


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
