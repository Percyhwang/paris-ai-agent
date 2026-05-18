import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_current_user
from app.core.i18n import normalize_language
from app.core.responses import api_ok
from app.db.mongodb import get_database, get_optional_database
from app.schemas.trips import TripAgentModifyRequest, TripCreate, TripGenerateRequest, TripUpdate
from app.services.agent_orchestrator_service import orchestrate_modify_itinerary
from app.services.agent_service import generate_trip_payload, modify_trip_with_agent
from app.services.trip_service import create_generated_trip, create_trip, delete_trip, get_trip_detail, list_user_trips, update_trip

router = APIRouter()
logger = logging.getLogger(__name__)

_GENERATION_JOBS: dict[str, dict[str, Any]] = {}
_MAX_GENERATION_JOBS = 100


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _trim_generation_jobs() -> None:
    if len(_GENERATION_JOBS) <= _MAX_GENERATION_JOBS:
        return
    for job_id, _ in sorted(_GENERATION_JOBS.items(), key=lambda item: str(item[1].get("created_at")))[:20]:
        _GENERATION_JOBS.pop(job_id, None)


def _public_generation_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "stage": job["stage"],
        "progress": job["progress"],
        "message": job["message"],
        "trip_id": job.get("trip_id"),
        "trip": job.get("trip"),
        "error": job.get("error"),
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "completed_at": job.get("completed_at"),
    }


def _update_generation_job(job_id: str, **updates: Any) -> None:
    job = _GENERATION_JOBS[job_id]
    job.update(updates)
    job["updated_at"] = _utc_now_iso()
    logger.info(
        "trip_generation_job job_id=%s status=%s stage=%s progress=%s message=%s",
        job_id,
        job.get("status"),
        job.get("stage"),
        job.get("progress"),
        job.get("message"),
    )


async def _run_generation_job(
    *,
    job_id: str,
    payload: TripGenerateRequest,
    user_id: str,
    db: AsyncIOMotorDatabase,
    language: str,
) -> None:
    try:
        _update_generation_job(
            job_id,
            status="running",
            stage="planning_brief",
            progress=15,
            message="Structuring your request into a Planning Brief.",
        )
        generated = await generate_trip_payload(payload, language=language, db=db, user_id=user_id)
        _update_generation_job(
            job_id,
            stage="saving",
            progress=88,
            message="Saving the validated itinerary to MongoDB.",
        )
        trip = await create_generated_trip(db, user_id, generated)
        _update_generation_job(
            job_id,
            status="completed",
            stage="completed",
            progress=100,
            message="Trip generated and saved.",
            trip_id=trip["id"],
            trip=trip,
            completed_at=_utc_now_iso(),
        )
    except HTTPException as exc:
        detail = str(exc.detail)
        _update_generation_job(
            job_id,
            status="failed",
            stage="failed",
            progress=100,
            message="Trip generation failed.",
            error=detail,
            completed_at=_utc_now_iso(),
        )
    except Exception as exc:
        logger.exception("trip_generation_job failed job_id=%s", job_id)
        _update_generation_job(
            job_id,
            status="failed",
            stage="failed",
            progress=100,
            message="Trip generation failed.",
            error=str(exc),
            completed_at=_utc_now_iso(),
        )


@router.post("/generate")
async def generate_trip(
    request: Request,
    payload: TripGenerateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    language = normalize_language(request.headers.get("accept-language"))
    generated = await generate_trip_payload(payload, language=language, db=db, user_id=current_user["id"])
    trip = await create_generated_trip(db, current_user["id"], generated)
    return api_ok(trip, "Trip generated")


@router.post("/generate/jobs")
async def start_generate_trip_job(
    request: Request,
    payload: TripGenerateRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    _trim_generation_jobs()
    job_id = str(uuid4())
    now = _utc_now_iso()
    _GENERATION_JOBS[job_id] = {
        "job_id": job_id,
        "user_id": current_user["id"],
        "status": "queued",
        "stage": "queued",
        "progress": 5,
        "message": "Queued trip generation.",
        "trip_id": None,
        "trip": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
    }
    language = normalize_language(request.headers.get("accept-language"))
    background_tasks.add_task(
        _run_generation_job,
        job_id=job_id,
        payload=payload,
        user_id=current_user["id"],
        db=db,
        language=language,
    )
    return api_ok(_public_generation_job(_GENERATION_JOBS[job_id]), "Trip generation queued")


@router.get("/generate/jobs/{job_id}")
async def get_generate_trip_job(
    job_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    job = _GENERATION_JOBS.get(job_id)
    if not job or job.get("user_id") != current_user["id"]:
        raise HTTPException(status_code=404, detail="Generation job not found")
    return api_ok(_public_generation_job(job))


@router.post("")
async def create_trip_route(
    payload: TripCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    trip = await create_trip(db, current_user["id"], payload)
    return api_ok(trip, "Trip created")


@router.get("")
async def list_trips_route(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase | None = Depends(get_optional_database),
) -> dict:
    if db is None:
        return api_ok([])

    language = normalize_language(request.headers.get("accept-language"))
    return api_ok(await list_user_trips(db, current_user["id"], language=language))


@router.get("/{trip_id}")
async def get_trip_route(
    request: Request,
    trip_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    language = normalize_language(request.headers.get("accept-language"))
    return api_ok(await get_trip_detail(db, current_user["id"], trip_id, language=language))


@router.patch("/{trip_id}")
async def patch_trip_route(
    trip_id: str,
    payload: TripUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    trip = await update_trip(db, current_user["id"], trip_id, payload)
    return api_ok(trip, "Trip updated")


@router.post("/{trip_id}/agent-modify")
async def agent_modify_trip_route(
    request: Request,
    trip_id: str,
    payload: TripAgentModifyRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    language = normalize_language(request.headers.get("accept-language"))
    trip = await orchestrate_modify_itinerary(
        payload,
        context={
            "entrypoint": "backend.trips.agent_modify",
            "trip_id": trip_id,
            "target_day": payload.target_day,
            "language": language,
        },
        execute_modify=lambda next_payload: modify_trip_with_agent(db, current_user["id"], trip_id, next_payload, language=language),
    )
    return api_ok(trip, "Trip modified by agent")


@router.delete("/{trip_id}")
async def delete_trip_route(
    trip_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    await delete_trip(db, current_user["id"], trip_id)
    return api_ok({"deleted": True}, "Trip deleted")
