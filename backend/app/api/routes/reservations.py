from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_current_user
from app.core.responses import api_ok
from app.db.mongodb import get_database
from app.db.serializers import serialize_doc, serialize_many
from app.schemas.reservations import ReservationCreate
from app.services.trip_service import ensure_trip_ownership

router = APIRouter()


@router.get("/{trip_id}/reservations")
async def list_reservations_route(
    trip_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    await ensure_trip_ownership(db, current_user["id"], trip_id)
    docs = await db.reservation_summary.find({"trip_id": trip_id}).sort("start_date", 1).to_list(length=100)
    return api_ok(serialize_many(docs))


@router.post("/{trip_id}/reservations")
async def create_reservation_route(
    trip_id: str,
    payload: ReservationCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    await ensure_trip_ownership(db, current_user["id"], trip_id)
    now = datetime.now(UTC)
    doc = payload.model_dump(mode="json")
    doc |= {"trip_id": trip_id, "user_id": current_user["id"], "created_at": now, "updated_at": now}
    result = await db.reservation_summary.insert_one(doc)
    created = await db.reservation_summary.find_one({"_id": result.inserted_id})
    return api_ok(serialize_doc(created), "Reservation created")
