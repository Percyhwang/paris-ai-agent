from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.data.places import SAMPLE_PLACES
from app.db.serializers import serialize_doc, serialize_many


async def ensure_place_seed_data(db: AsyncIOMotorDatabase) -> None:
    if await db.place_catalog.count_documents({}) > 0:
        return
    await db.place_catalog.insert_many(SAMPLE_PLACES)


async def list_places(
    db: AsyncIOMotorDatabase,
    search: str | None = None,
    category: str | None = None,
    sort: str = "popular",
) -> list[dict]:
    query: dict = {}
    if category and category != "all":
        query["category"] = category
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"short_description": {"$regex": search, "$options": "i"}},
            {"tags": {"$regex": search, "$options": "i"}},
        ]

    sort_clause = [("popularity", -1)] if sort == "popular" else [("name", 1)]
    docs = await db.place_catalog.find(query).sort(sort_clause).to_list(length=100)
    return serialize_many(docs)


async def get_place(db: AsyncIOMotorDatabase, place_id: str) -> dict:
    query = {"_id": ObjectId(place_id)} if ObjectId.is_valid(place_id) else {"slug": place_id}
    doc = await db.place_catalog.find_one(query)
    if not doc:
        raise HTTPException(status_code=404, detail="Place not found")
    return serialize_doc(doc)
