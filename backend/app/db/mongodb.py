import logging

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

client: AsyncIOMotorClient | None = None
database: AsyncIOMotorDatabase | None = None
mongo_startup_error: str | None = None

logger = logging.getLogger(__name__)


async def connect_to_mongo() -> None:
    global client, database, mongo_startup_error

    try:
        client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=8000)
        database = client[settings.mongodb_db]
        await database.command("ping")
        await _ensure_indexes(database)
        mongo_startup_error = None
    except Exception as exc:
        mongo_startup_error = str(exc)
        logger.warning("MongoDB startup connection failed; continuing without database: %s", exc)
        if client:
            client.close()
        client = None
        database = None


async def close_mongo_connection() -> None:
    global client, database
    if client:
        client.close()
    client = None
    database = None


def get_database() -> AsyncIOMotorDatabase:
    if database is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return database


def get_optional_database() -> AsyncIOMotorDatabase | None:
    return database


def get_database_status() -> dict[str, str | bool | None]:
    return {
        "available": database is not None,
        "database": settings.mongodb_db,
        "error": mongo_startup_error,
    }


async def _ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.users.create_index("google_id", unique=True)
    await db.users.create_index("email", unique=True)
    await db.trip_plans.create_index([("user_id", 1), ("created_at", -1)])
    await db.itinerary_day.create_index([("trip_id", 1), ("day_number", 1)])
    await db.reservation_summary.create_index([("trip_id", 1), ("start_date", 1)])
    await db.budget_summary.create_index("trip_id", unique=True)
    await db.diary_entry.create_index([("trip_id", 1), ("entry_date", -1)])
    await db.weather_cache.create_index("expires_at", expireAfterSeconds=0)
