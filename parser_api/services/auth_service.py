from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from parser_api.schemas import AuthResponsePayload, AuthUserPayload, TokenPairPayload

ACCESS_TOKEN_LIFETIME_SECONDS = 60 * 60
REFRESH_TOKEN_LIFETIME_SECONDS = 60 * 60 * 24 * 30
ALLOWED_GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
GOOGLE_AUTH_VERIFICATION_MODES = {
    "tokeninfo",
    "tokeninfo_or_jwt",
    "jwt_payload",
}

USER_STATE: dict[str, dict] = {}
USER_BY_GOOGLE_ID: dict[str, str] = {}


class AuthError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: object | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _get_google_client_id() -> str:
    return (
        os.getenv("GOOGLE_CLIENT_ID")
        or os.getenv("VITE_GOOGLE_CLIENT_ID")
        or ""
    ).strip()


def _get_auth_secret() -> str:
    return (os.getenv("AUTH_SECRET") or "paris-ai-agent-dev-secret").strip()


def _get_google_auth_verification_mode() -> str:
    mode = (os.getenv("GOOGLE_AUTH_VERIFICATION_MODE") or "tokeninfo").strip().lower()
    if mode in GOOGLE_AUTH_VERIFICATION_MODES:
        return mode
    return "tokeninfo"


def _allow_insecure_dev_auth() -> bool:
    return (os.getenv("ALLOW_INSECURE_DEV_AUTH") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("utf-8")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(f"{raw}{padding}")


def _default_preferences() -> dict[str, object]:
    return {
        "travel_style": [],
        "favorite_categories": [],
        "budget_currency": "EUR",
        "language": "ko",
    }


def _sign(data: str) -> str:
    signature = hmac.new(
        _get_auth_secret().encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64url_encode(signature)


def _encode_token(payload: dict[str, object]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_segment = _b64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    payload_segment = _b64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature_segment = _sign(f"{header_segment}.{payload_segment}")
    return f"{header_segment}.{payload_segment}.{signature_segment}"


def _decode_token(token: str, expected_type: str) -> dict[str, object]:
    try:
        header_segment, payload_segment, signature_segment = token.split(".")
    except ValueError as exc:
        raise AuthError(
            status_code=401,
            code="INVALID_TOKEN_FORMAT",
            message="Token format is invalid.",
        ) from exc

    expected_signature = _sign(f"{header_segment}.{payload_segment}")
    if not hmac.compare_digest(signature_segment, expected_signature):
        raise AuthError(
            status_code=401,
            code="INVALID_TOKEN_SIGNATURE",
            message="Token signature is invalid.",
        )

    try:
        payload = json.loads(_b64url_decode(payload_segment))
    except (json.JSONDecodeError, ValueError) as exc:
        raise AuthError(
            status_code=401,
            code="INVALID_TOKEN_PAYLOAD",
            message="Token payload is invalid.",
        ) from exc

    if payload.get("typ") != expected_type:
        raise AuthError(
            status_code=401,
            code=f"INVALID_{expected_type.upper()}_TOKEN",
            message=f"{expected_type.title()} token is invalid.",
        )

    try:
        expires_at = int(payload["exp"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthError(
            status_code=401,
            code="TOKEN_EXPIRY_MISSING",
            message="Token expiry is missing.",
        ) from exc

    if expires_at <= int(_now().timestamp()):
        raise AuthError(
            status_code=401,
            code="TOKEN_EXPIRED",
            message="Token has expired.",
        )

    return payload


def _issue_token_pair(user_id: str) -> TokenPairPayload:
    issued_at = int(_now().timestamp())
    access_payload = {
        "sub": user_id,
        "typ": "access",
        "iat": issued_at,
        "exp": issued_at + ACCESS_TOKEN_LIFETIME_SECONDS,
        "jti": str(uuid4()),
    }
    refresh_payload = {
        "sub": user_id,
        "typ": "refresh",
        "iat": issued_at,
        "exp": issued_at + REFRESH_TOKEN_LIFETIME_SECONDS,
        "jti": str(uuid4()),
    }
    return TokenPairPayload(
        access_token=_encode_token(access_payload),
        refresh_token=_encode_token(refresh_payload),
        token_type="bearer",
        expires_in=ACCESS_TOKEN_LIFETIME_SECONDS,
    )


def _derive_name_from_email(email: str) -> str:
    local_part = email.split("@", 1)[0]
    if not local_part:
        return "Paris Traveler"
    return " ".join(part.capitalize() for part in local_part.replace(".", " ").split())


def _upsert_user(
    *,
    google_id: str,
    email: str,
    name: str | None,
    profile_image: str | None,
) -> AuthUserPayload:
    user_id = USER_BY_GOOGLE_ID.get(google_id)
    now = _now_iso()
    if user_id and user_id in USER_STATE:
        user = dict(USER_STATE[user_id])
        user["email"] = email
        user["name"] = name or user["name"]
        user["profile_image"] = profile_image
        user["updated_at"] = now
    else:
        user_id = str(uuid4())
        user = {
            "id": user_id,
            "google_id": google_id,
            "email": email,
            "name": name or _derive_name_from_email(email),
            "profile_image": profile_image,
            "preferences": _default_preferences(),
            "trips": [],
            "created_at": now,
            "updated_at": now,
        }

    USER_BY_GOOGLE_ID[google_id] = user_id
    USER_STATE[user_id] = deepcopy(user)
    return AuthUserPayload.model_validate(user)


def _normalize_google_identity(payload: dict[str, object]) -> dict[str, str | None]:
    email = str(payload.get("email") or "").strip()
    google_id = str(payload.get("sub") or "").strip()
    if not email or not google_id:
        raise AuthError(
            status_code=401,
            code="GOOGLE_PROFILE_INCOMPLETE",
            message="Google profile is missing required fields.",
        )

    return {
        "google_id": google_id,
        "email": email,
        "name": str(payload.get("name") or "").strip() or None,
        "profile_image": str(payload.get("picture") or "").strip() or None,
    }


def _decode_google_jwt_payload_unverified(credential: str) -> dict[str, object]:
    try:
        _, payload_segment, _ = credential.split(".")
    except ValueError as exc:
        raise AuthError(
            status_code=401,
            code="INVALID_GOOGLE_CREDENTIAL",
            message="Google credential verification failed.",
        ) from exc

    try:
        payload = json.loads(_b64url_decode(payload_segment))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise AuthError(
            status_code=401,
            code="INVALID_GOOGLE_CREDENTIAL",
            message="Google credential verification failed.",
        ) from exc

    if not isinstance(payload, dict):
        raise AuthError(
            status_code=401,
            code="INVALID_GOOGLE_CREDENTIAL",
            message="Google credential verification failed.",
        )

    return payload


def _google_audience_matches(payload: dict[str, object], client_id: str) -> bool:
    audience = payload.get("aud")
    if isinstance(audience, list):
        audiences = {str(value).strip() for value in audience if str(value).strip()}
    else:
        audiences = {str(audience).strip()} if str(audience or "").strip() else set()

    authorized_party = str(payload.get("azp") or "").strip()
    return client_id in audiences or authorized_party == client_id


def _validate_google_identity_payload(
    payload: dict[str, object],
    *,
    client_id: str,
) -> dict[str, str | None]:
    if not _google_audience_matches(payload, client_id):
        raise AuthError(
            status_code=401,
            code="GOOGLE_AUDIENCE_MISMATCH",
            message="Google credential audience does not match the configured client id.",
        )

    if str(payload.get("iss") or "").strip() not in ALLOWED_GOOGLE_ISSUERS:
        raise AuthError(
            status_code=401,
            code="GOOGLE_ISSUER_INVALID",
            message="Google credential issuer is invalid.",
        )

    if str(payload.get("email_verified") or "").lower() not in {"true", "1"}:
        raise AuthError(
            status_code=401,
            code="GOOGLE_EMAIL_NOT_VERIFIED",
            message="Google account email is not verified.",
        )

    try:
        expires_at = int(payload.get("exp") or 0)
    except (TypeError, ValueError) as exc:
        raise AuthError(
            status_code=401,
            code="GOOGLE_CREDENTIAL_EXPIRED",
            message="Google credential has expired.",
        ) from exc

    if expires_at <= int(_now().timestamp()):
        raise AuthError(
            status_code=401,
            code="GOOGLE_CREDENTIAL_EXPIRED",
            message="Google credential has expired.",
        )

    return _normalize_google_identity(payload)


def _verify_demo_credential(credential: str) -> dict[str, str | None]:
    email = credential.removeprefix("dev:").strip()
    if not email or "@" not in email:
        raise AuthError(
            status_code=400,
            code="INVALID_DEMO_CREDENTIAL",
            message="Demo credential must include an email address.",
        )
    return {
        "google_id": f"dev:{email}",
        "email": email,
        "name": _derive_name_from_email(email),
        "profile_image": None,
    }


def _verify_google_credential(credential: str) -> dict[str, str | None]:
    if credential.startswith("dev:"):
        return _verify_demo_credential(credential)

    client_id = _get_google_client_id()
    verification_mode = _get_google_auth_verification_mode()
    if _allow_insecure_dev_auth():
        payload = _decode_google_jwt_payload_unverified(credential)
        if client_id:
            return _validate_google_identity_payload(payload, client_id=client_id)
        return _normalize_google_identity(payload)
    if not client_id:
        raise AuthError(
            status_code=500,
            code="GOOGLE_CLIENT_ID_NOT_CONFIGURED",
            message="Google OAuth client id is not configured on the server.",
        )

    if verification_mode == "jwt_payload":
        return _validate_google_identity_payload(
            _decode_google_jwt_payload_unverified(credential),
            client_id=client_id,
        )

    try:
        response = httpx.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": credential},
            timeout=5.0,
        )
    except httpx.HTTPError as exc:
        if verification_mode == "tokeninfo_or_jwt":
            return _validate_google_identity_payload(
                _decode_google_jwt_payload_unverified(credential),
                client_id=client_id,
            )
        raise AuthError(
            status_code=502,
            code="GOOGLE_TOKENINFO_REQUEST_FAILED",
            message="Failed to verify Google credential.",
            details=str(exc),
        ) from exc

    if response.status_code != 200:
        raise AuthError(
            status_code=401,
            code="INVALID_GOOGLE_CREDENTIAL",
            message="Google credential verification failed.",
            details=response.text,
        )

    return _validate_google_identity_payload(response.json(), client_id=client_id)


def login_with_google_credential(credential: str) -> AuthResponsePayload:
    identity = _verify_google_credential(credential)
    user = _upsert_user(**identity)
    tokens = _issue_token_pair(user.id)
    return AuthResponsePayload(user=user, tokens=tokens)


def get_user_from_access_token(access_token: str) -> AuthUserPayload:
    payload = _decode_token(access_token, "access")
    user_id = str(payload.get("sub") or "")
    user = USER_STATE.get(user_id)
    if user is None:
        raise AuthError(
            status_code=401,
            code="USER_NOT_FOUND",
            message="Authenticated user was not found.",
        )
    return AuthUserPayload.model_validate(deepcopy(user))


def refresh_tokens(refresh_token: str) -> TokenPairPayload:
    payload = _decode_token(refresh_token, "refresh")
    user_id = str(payload.get("sub") or "")
    if user_id not in USER_STATE:
        raise AuthError(
            status_code=401,
            code="USER_NOT_FOUND",
            message="Authenticated user was not found.",
        )
    return _issue_token_pair(user_id)


def reset_auth_state() -> None:
    USER_STATE.clear()
    USER_BY_GOOGLE_ID.clear()
