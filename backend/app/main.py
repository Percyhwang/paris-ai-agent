from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import api_router
from app.core.config import settings
from app.core.responses import api_error, api_ok
from app.db.mongodb import close_mongo_connection, connect_to_mongo, get_database
from app.services.place_service import ensure_place_seed_data


app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    await connect_to_mongo()
    await ensure_place_seed_data(get_database())


@app.on_event("shutdown")
async def shutdown() -> None:
    await close_mongo_connection()


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=api_error(message=str(exc.detail), code=f"HTTP_{exc.status_code}"),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=api_error(message="Request validation failed", code="VALIDATION_ERROR", details=exc.errors()),
    )


@app.get("/health")
async def health() -> dict:
    return api_ok({"service": settings.app_name, "environment": settings.app_env})


app.include_router(api_router, prefix=settings.api_prefix)
