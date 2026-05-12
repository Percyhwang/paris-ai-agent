import os
from pathlib import Path

from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from parser_api.router import agent_run
from parser_api.schemas import (
    AgentRunRequest,
    AgentRunResponse,
    GoogleLoginRequest,
    TokenRefreshRequest,
)
from parser_api.services.auth_service import (
    AuthError,
    get_user_from_access_token,
    login_with_google_credential,
    refresh_tokens,
)
from parser_api.web_router import web_api

load_dotenv(Path(__file__).with_name(".env"))

app = FastAPI(title="Agent API")


def _cors_allow_origins() -> list[str]:
    defaults = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]
    configured = (os.getenv("CORS_ALLOW_ORIGINS") or "").strip()
    if configured:
        merged = [origin.strip() for origin in configured.split(",") if origin.strip()]
        for origin in defaults:
            if origin not in merged:
                merged.append(origin)
        return merged
    return defaults


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(web_api)


def _success_response(data: object, message: str = "OK") -> dict[str, object]:
    return {
        "success": True,
        "data": data,
        "message": message,
        "error": None,
    }


def _error_response(exc: AuthError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "data": None,
            "message": exc.message,
            "error": {
                "code": exc.code,
                "details": exc.details,
            },
        },
    )


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise AuthError(
            status_code=401,
            code="AUTHORIZATION_MISSING",
            message="Authorization header is required.",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthError(
            status_code=401,
            code="AUTHORIZATION_INVALID",
            message="Authorization header must use Bearer token format.",
        )
    return token


@app.post("/agent/run", response_model=AgentRunResponse)
@app.post("/api/agent/run", response_model=AgentRunResponse)
def agent_run_endpoint(payload: AgentRunRequest) -> AgentRunResponse:
    return agent_run(payload)


@app.post("/api/auth/google/login")
def google_login_endpoint(payload: GoogleLoginRequest):
    try:
        response = login_with_google_credential(payload.credential)
    except AuthError as exc:
        return _error_response(exc)
    return _success_response(response.model_dump(), "Google login successful.")


@app.post("/api/auth/refresh")
def refresh_auth_endpoint(payload: TokenRefreshRequest):
    try:
        tokens = refresh_tokens(payload.refresh_token)
    except AuthError as exc:
        return _error_response(exc)
    return _success_response(tokens.model_dump(), "Access token refreshed.")


@app.get("/api/auth/me")
def auth_me_endpoint(authorization: str | None = Header(default=None)):
    try:
        token = _extract_bearer_token(authorization)
        user = get_user_from_access_token(token)
    except AuthError as exc:
        return _error_response(exc)
    return _success_response(user.model_dump(), "Authenticated user loaded.")
