from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_current_user
from app.core.responses import api_ok
from app.db.mongodb import get_database
from app.schemas.trips import ItineraryUpdate
from app.services.trip_service import get_itinerary, replace_itinerary

router = APIRouter()


@router.get("/{trip_id}/itinerary")
async def get_itinerary_route(
    trip_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    return api_ok(await get_itinerary(db, current_user["id"], trip_id))


@router.put("/{trip_id}/itinerary")
async def put_itinerary_route(
    trip_id: str,
    payload: ItineraryUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    days = await replace_itinerary(db, current_user["id"], trip_id, payload)
    return api_ok(days, "Itinerary updated")
