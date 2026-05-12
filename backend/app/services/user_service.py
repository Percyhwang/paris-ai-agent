from datetime import UTC, datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.db.serializers import serialize_doc
from app.schemas.users import GoogleProfile, UserUpdate

memory_users_by_id: dict[str, dict] = {}
memory_user_ids_by_google_id: dict[str, str] = {}


async def upsert_google_user(db: AsyncIOMotorDatabase | None, profile: GoogleProfile) -> dict:
    if db is None:
        return upsert_memory_google_user(profile)

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


async def update_user_profile(db: AsyncIOMotorDatabase | None, user_id: str, payload: UserUpdate) -> dict:
    if db is None:
        return update_memory_user(user_id, payload.model_dump(exclude_unset=True))

    update = payload.model_dump(exclude_unset=True)
    update["updated_at"] = datetime.now(UTC)
    user = await db.users.find_one_and_update(
        {"_id": ObjectId(user_id)},
        {"$set": update},
        return_document=ReturnDocument.AFTER,
    )
    return serialize_doc(user)


def upsert_memory_google_user(profile: GoogleProfile) -> dict:
    now = datetime.now(UTC).isoformat()
    user_id = memory_user_ids_by_google_id.get(profile.google_id) or str(ObjectId())
    existing = memory_users_by_id.get(user_id, {})
    user = {
        **existing,
        "id": user_id,
        "google_id": profile.google_id,
        "email": profile.email,
        "name": profile.name,
        "profile_image": profile.profile_image,
        "preferences": existing.get(
            "preferences",
            {
                "travel_style": [],
                "favorite_categories": [],
                "budget_currency": "EUR",
                "language": "ko",
            },
        ),
        "trips": existing.get("trips", []),
        "created_at": existing.get("created_at", now),
        "updated_at": now,
    }
    memory_user_ids_by_google_id[profile.google_id] = user_id
    memory_users_by_id[user_id] = user
    return dict(user)


def get_memory_user(user_id: str) -> dict | None:
    user = memory_users_by_id.get(user_id)
    return dict(user) if user else None


def update_memory_user(user_id: str, update: dict) -> dict:
    user = memory_users_by_id.get(user_id)
    if not user:
        return {}
    updated = {**user, **update, "updated_at": datetime.now(UTC).isoformat()}
    memory_users_by_id[user_id] = updated
    return dict(updated)


def set_memory_refresh_hash(user_id: str, refresh_token_hash: str) -> None:
    user = memory_users_by_id.get(user_id)
    if user:
        memory_users_by_id[user_id] = {**user, "refresh_token_hash": refresh_token_hash}
