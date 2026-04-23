from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

client: AsyncIOMotorClient | None = None
database: AsyncIOMotorDatabase | None = None


async def connect_to_mongo() -> None:
    global client, database
    client = AsyncIOMotorClient(settings.mongodb_uri)
    database = client[settings.mongodb_db]
    await database.command("ping")
    await _ensure_indexes(database)


async def close_mongo_connection() -> None:
    if client:
        client.close()


def get_database() -> AsyncIOMotorDatabase:
    if database is None:
        raise RuntimeError("MongoDB is not initialized")
    return database


async def _ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.users.create_index("google_id", unique=True)
    await db.users.create_index("email", unique=True)
    await db.trip_plans.create_index([("user_id", 1), ("created_at", -1)])
    await db.itinerary_day.create_index([("trip_id", 1), ("day_number", 1)])
    await db.reservation_summary.create_index([("trip_id", 1), ("start_date", 1)])
    await db.budget_summary.create_index("trip_id", unique=True)
    await db.diary_entry.create_index([("trip_id", 1), ("entry_date", -1)])
    await db.place_catalog.create_index("slug", unique=True)
    await db.place_catalog.create_index([("name", "text"), ("short_description", "text"), ("tags", "text")])
    await db.weather_cache.create_index("expires_at", expireAfterSeconds=0)
