from bson import ObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.security import decode_token
from app.db.mongodb import get_optional_database
from app.db.serializers import serialize_doc
from app.services.user_service import get_memory_user

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/google/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncIOMotorDatabase | None = Depends(get_optional_database),
) -> dict:
    payload = decode_token(token, expected_type="access")
    user_id = payload.get("sub")
    if not user_id or not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user")

    if db is None:
        user = get_memory_user(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user

    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return serialize_doc(user)
