from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _now() -> datetime:
    return datetime.now(UTC)


async def load_trip_state(db: Any | None, *, user_id: str, trip_id: str) -> dict[str, Any] | None:
    if db is None or not trip_id:
        return None
    doc = await db.trip_state.find_one({"trip_id": str(trip_id), "user_id": str(user_id)})
    return dict(doc) if isinstance(doc, dict) else None


async def update_trip_state(
    db: Any | None,
    *,
    user_id: str,
    trip_id: str,
    patch: dict[str, Any],
    event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if db is None or not trip_id:
        return {"updated": False, "reason": "missing_db_or_trip_id"}

    now = _now()
    update: dict[str, Any] = {
        "$set": {
            "trip_id": str(trip_id),
            "user_id": str(user_id),
            "updated_at": now,
            **patch,
        },
        "$setOnInsert": {"created_at": now},
    }
    if event:
        update["$push"] = {"events": {"timestamp": now, **event}}
    await db.trip_state.update_one(
        {"trip_id": str(trip_id), "user_id": str(user_id)},
        update,
        upsert=True,
    )
    return {"updated": True, "trip_id": str(trip_id)}


async def save_itinerary_state(
    db: Any | None,
    *,
    user_id: str,
    trip_id: str,
    trip: dict[str, Any],
    itinerary_days: list[dict[str, Any]],
) -> dict[str, Any]:
    return await update_trip_state(
        db,
        user_id=user_id,
        trip_id=trip_id,
        patch={
            "destination": "Paris",
            "dates": {"start_date": trip.get("start_date"), "end_date": trip.get("end_date"), "days": trip.get("total_days")},
            "planning_brief": trip.get("planning_brief"),
            "itinerary": itinerary_days,
            "route_legs": trip.get("route_legs") or [],
            "constraints": trip.get("constraint_validation"),
            "memory_context": trip.get("memory_context"),
            "evaluation_history": [trip.get("agent_evaluation")] if trip.get("agent_evaluation") else [],
        },
        event={"type": "itinerary_saved", "status": trip.get("status")},
    )


async def save_hotel_candidates(
    db: Any | None,
    *,
    user_id: str,
    trip_id: str | None,
    candidates: list[dict[str, Any]],
    search_conditions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not trip_id:
        return {"updated": False, "reason": "missing_trip_id"}
    return await update_trip_state(
        db,
        user_id=user_id,
        trip_id=trip_id,
        patch={"hotel_candidates": candidates, "hotel_search_conditions": search_conditions or {}},
        event={"type": "hotel_candidates_saved", "candidate_count": len(candidates)},
    )


async def save_flight_candidates(
    db: Any | None,
    *,
    user_id: str,
    trip_id: str | None,
    candidates: list[dict[str, Any]],
    search_conditions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not trip_id:
        return {"updated": False, "reason": "missing_trip_id"}
    return await update_trip_state(
        db,
        user_id=user_id,
        trip_id=trip_id,
        patch={"flight_candidates": candidates, "flight_search_conditions": search_conditions or {}},
        event={"type": "flight_candidates_saved", "candidate_count": len(candidates)},
    )

