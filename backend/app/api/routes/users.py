from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_current_user
from app.core.responses import api_ok
from app.db.mongodb import get_optional_database
from app.schemas.users import UserUpdate
from app.services.user_service import update_user_profile

router = APIRouter()


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)) -> dict:
    return api_ok(current_user)


@router.patch("/me")
async def patch_me(
    payload: UserUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase | None = Depends(get_optional_database),
) -> dict:
    user = await update_user_profile(db, current_user["id"], payload)
    return api_ok(user, "Profile updated")
