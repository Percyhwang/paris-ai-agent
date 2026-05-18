import logging
from typing import Any

import httpx
from fastapi import HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.core.config import settings
from app.schemas.users import GoogleProfile

logger = logging.getLogger(__name__)
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


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
            clock_skew_in_seconds=300,
        )
    except ValueError as exc:
        logger.warning("Local Google credential verification failed: %s", exc)
        token_info = await _verify_google_credential_with_tokeninfo(credential)

    return GoogleProfile(
        google_id=token_info["sub"],
        email=token_info["email"],
        name=token_info.get("name") or token_info["email"].split("@")[0],
        profile_image=token_info.get("picture"),
        raw=token_info,
    )


async def _verify_google_credential_with_tokeninfo(credential: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(GOOGLE_TOKENINFO_URL, params={"id_token": credential})
    except httpx.HTTPError as exc:
        logger.warning("Google tokeninfo request failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google credential") from exc

    if response.is_error:
        logger.warning("Google tokeninfo rejected credential: status=%s", response.status_code)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google credential")

    try:
        token_info = response.json()
    except ValueError as exc:
        logger.warning("Google tokeninfo returned malformed JSON")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google credential") from exc

    if token_info.get("aud") != settings.google_client_id:
        logger.warning("Google token audience mismatch")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google credential")
    if not token_info.get("sub") or not token_info.get("email"):
        logger.warning("Google tokeninfo missing required profile fields")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google credential")

    return token_info
