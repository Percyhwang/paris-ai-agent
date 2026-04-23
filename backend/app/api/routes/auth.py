from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.responses import api_ok
from app.core.security import create_access_token, create_refresh_token, decode_token, hash_token
from app.db.mongodb import get_database
from app.schemas.auth import GoogleLoginRequest, RefreshTokenRequest
from app.services.auth_service import verify_google_credential
from app.services.user_service import upsert_google_user

router = APIRouter()


@router.post("/google/login")
async def google_login(
    payload: GoogleLoginRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    profile = await verify_google_credential(payload.credential)
    user = await upsert_google_user(db, profile)
    access_token = create_access_token(user["id"])
    refresh_token = create_refresh_token(user["id"])
    await db.users.update_one(
        {"_id": ObjectId(user["id"])},
        {"$set": {"refresh_token_hash": hash_token(refresh_token)}},
    )
    return api_ok(
        {
            "user": user,
            "tokens": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": settings.access_token_expire_minutes * 60,
            },
        },
        "Logged in",
    )


@router.post("/refresh")
async def refresh_token(
    payload: RefreshTokenRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    token_payload = decode_token(payload.refresh_token, expected_type="refresh")
    user_id = token_payload.get("sub")
    if not user_id or not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user or user.get("refresh_token_hash") != hash_token(payload.refresh_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")

    access_token = create_access_token(user_id)
    new_refresh_token = create_refresh_token(user_id)
    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"refresh_token_hash": hash_token(new_refresh_token)}},
    )
    return api_ok(
        {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
        },
        "Token refreshed",
    )


@router.get("/me")
async def auth_me(current_user: dict = Depends(get_current_user)) -> dict:
    return api_ok(current_user)
