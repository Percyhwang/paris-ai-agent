from datetime import UTC, datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.db.serializers import serialize_doc
from app.schemas.users import GoogleProfile, UserUpdate


async def upsert_google_user(db: AsyncIOMotorDatabase, profile: GoogleProfile) -> dict:
    now = datetime.now(UTC)
    user = await db.users.find_one_and_update(
        {"google_id": profile.google_id},
        {
            "$set": {
                "email": profile.email,
                "name": profile.name,
                "profile_image": profile.profile_image,
                "updated_at": now,
            },
            "$setOnInsert": {
                "google_id": profile.google_id,
                "preferences": {
                    "travel_style": [],
                    "favorite_categories": [],
                    "budget_currency": "EUR",
                    "language": "ko",
                },
                "trips": [],
                "created_at": now,
            },
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return serialize_doc(user)


async def update_user_profile(db: AsyncIOMotorDatabase, user_id: str, payload: UserUpdate) -> dict:
    update = payload.model_dump(exclude_unset=True)
    update["updated_at"] = datetime.now(UTC)
    user = await db.users.find_one_and_update(
        {"_id": ObjectId(user_id)},
        {"$set": update},
        return_document=ReturnDocument.AFTER,
    )
    return serialize_doc(user)
