from fastapi import APIRouter, Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_current_user
from app.core.i18n import normalize_language
from app.core.responses import api_ok
from app.db.mongodb import get_database
from app.schemas.diary import DiaryCreate, DiaryGenerateRequest
from app.services.diary_service import create_diary_entry, generate_diary, list_diary_entries

router = APIRouter()


@router.post("/{trip_id}/diary")
async def create_diary_route(
    trip_id: str,
    payload: DiaryCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    entry = await create_diary_entry(db, current_user["id"], trip_id, payload)
    return api_ok(entry, "Diary saved")


@router.get("/{trip_id}/diary")
async def list_diary_route(
    trip_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    return api_ok(await list_diary_entries(db, current_user["id"], trip_id))


@router.post("/{trip_id}/diary/generate")
async def generate_diary_route(
    request: Request,
    trip_id: str,
    payload: DiaryGenerateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    from app.services.trip_service import ensure_trip_ownership

    await ensure_trip_ownership(db, current_user["id"], trip_id)
    language = normalize_language(request.headers.get("accept-language"))
    generated = await generate_diary(payload, language=language)
    return api_ok(generated, "Diary generated")
