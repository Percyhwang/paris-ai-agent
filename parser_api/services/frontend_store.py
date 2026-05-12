from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

BUDGET_STATE: dict[str, dict] = {}
DIARY_STATE: dict[str, list[dict]] = {}
RESERVATION_STATE: dict[str, list[dict]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_budget_state(trip_id: str) -> dict | None:
    state = BUDGET_STATE.get(trip_id)
    return dict(state) if state is not None else None


def set_budget_state(trip_id: str, state: dict) -> dict:
    payload = dict(state)
    payload["last_updated"] = _now_iso()
    BUDGET_STATE[trip_id] = payload
    return dict(payload)


def list_diary_entries(trip_id: str) -> list[dict]:
    return [dict(entry) for entry in DIARY_STATE.get(trip_id, [])]


def create_diary_entry(trip_id: str, payload: dict) -> dict:
    entry = {
        "id": str(uuid4()),
        "trip_id": trip_id,
        "user_id": "local-demo-user",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        **payload,
    }
    DIARY_STATE.setdefault(trip_id, [])
    DIARY_STATE[trip_id].insert(0, entry)
    return dict(entry)


def list_reservations(trip_id: str) -> list[dict]:
    return [dict(item) for item in RESERVATION_STATE.get(trip_id, [])]


def create_reservation(trip_id: str, payload: dict) -> dict:
    reservation = {
        "id": str(uuid4()),
        "trip_id": trip_id,
        "user_id": "local-demo-user",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        **payload,
    }
    RESERVATION_STATE.setdefault(trip_id, [])
    RESERVATION_STATE[trip_id].insert(0, reservation)
    return dict(reservation)


def reset_frontend_store() -> None:
    BUDGET_STATE.clear()
    DIARY_STATE.clear()
    RESERVATION_STATE.clear()
