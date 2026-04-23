from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.responses import api_ok
from app.db.mongodb import get_database
from app.services.place_service import get_place, list_places

router = APIRouter()


@router.get("")
async def list_places_route(
    search: str | None = Query(default=None),
    category: str | None = Query(default=None),
    sort: str = Query(default="popular"),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    places = await list_places(db, search=search, category=category, sort=sort)
    return api_ok(places)


@router.get("/{place_id}")
async def get_place_route(
    place_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    return api_ok(await get_place(db, place_id))
