from fastapi import HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.core.config import settings
from app.schemas.users import GoogleProfile


async def verify_google_credential(credential: str) -> GoogleProfile:
    if credential.startswith("dev:"):
        if not settings.allow_insecure_dev_auth:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Dev auth is disabled")
        email = credential.replace("dev:", "", 1) or "paris.traveler@example.com"
        return GoogleProfile(
            google_id=f"dev-{email}",
            email=email,
            name="Paris Traveler",
            profile_image="https://api.dicebear.com/8.x/thumbs/svg?seed=paris",
            raw={"mode": "development"},
        )

    if not settings.google_client_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="GOOGLE_CLIENT_ID is not configured")

    try:
        token_info = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            settings.google_client_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google credential") from exc

    return GoogleProfile(
        google_id=token_info["sub"],
        email=token_info["email"],
        name=token_info.get("name") or token_info["email"].split("@")[0],
        profile_image=token_info.get("picture"),
        raw=token_info,
    )
