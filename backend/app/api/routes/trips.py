from fastapi import APIRouter, Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_current_user
from app.core.i18n import normalize_language
from app.core.responses import api_ok
from app.db.mongodb import get_database, get_optional_database
from app.schemas.trips import TripCreate, TripGenerateRequest, TripUpdate
from app.services.agent_service import generate_trip_payload
from app.services.trip_service import create_generated_trip, create_trip, delete_trip, get_trip_detail, list_user_trips, update_trip

router = APIRouter()


@router.post("/generate")
async def generate_trip(
    request: Request,
    payload: TripGenerateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    language = normalize_language(request.headers.get("accept-language"))
    generated = await generate_trip_payload(payload, language=language)
    trip = await create_generated_trip(db, current_user["id"], generated)
    return api_ok(trip, "Trip generated")


@router.post("")
async def create_trip_route(
    payload: TripCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    trip = await create_trip(db, current_user["id"], payload)
    return api_ok(trip, "Trip created")


@router.get("")
async def list_trips_route(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase | None = Depends(get_optional_database),
) -> dict:
    if db is None:
        return api_ok([])

    language = normalize_language(request.headers.get("accept-language"))
    return api_ok(await list_user_trips(db, current_user["id"], language=language))


@router.get("/{trip_id}")
async def get_trip_route(
    request: Request,
    trip_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    language = normalize_language(request.headers.get("accept-language"))
    return api_ok(await get_trip_detail(db, current_user["id"], trip_id, language=language))


@router.patch("/{trip_id}")
async def patch_trip_route(
    trip_id: str,
    payload: TripUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    trip = await update_trip(db, current_user["id"], trip_id, payload)
    return api_ok(trip, "Trip updated")


@router.delete("/{trip_id}")
async def delete_trip_route(
    trip_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    await delete_trip(db, current_user["id"], trip_id)
    return api_ok({"deleted": True}, "Trip deleted")
