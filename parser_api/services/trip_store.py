from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from parser_api.intents import Intent

# MVP in-memory trip state storage.
TRIP_STATE: dict[str, dict] = {}
SAVED_TRIPS: dict[str, dict] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _with_meta(meta: dict | None) -> dict:
    resolved = {"mcp": "stub"}
    if meta:
        resolved.update(meta)
    return resolved


def save_create_plan_trip(
    plan_payload: dict,
    meta: dict | None = None,
    extra_state: dict | None = None,
) -> tuple[str, dict]:
    trip_id = str(uuid4())
    now = _now_iso()
    trip_meta = _with_meta(meta)
    trip_meta.setdefault("created_at", now)
    trip_meta["updated_at"] = now
    trip_state = {
        "intent": Intent.CREATE_PLAN.value,
        "plan": plan_payload,
        "meta": trip_meta,
    }
    if extra_state:
        trip_state.update(deepcopy(extra_state))
    TRIP_STATE[trip_id] = trip_state
    return trip_id, trip_state


def save_modify_plan_trip(
    modify_payload: dict,
    meta: dict | None = None,
    extra_state: dict | None = None,
) -> tuple[str, dict]:
    trip_id = str(modify_payload.get("trip_id") or uuid4())
    existing_state = dict(TRIP_STATE.get(trip_id) or {})
    now = _now_iso()
    state_meta = dict(existing_state.get("meta") or {})
    state_meta.update(_with_meta(meta))
    state_meta.setdefault("created_at", now)
    state_meta["updated_at"] = now
    trip_state = {
        **existing_state,
        "intent": Intent.MODIFY_PLAN.value,
        "modify": modify_payload,
        "meta": state_meta,
    }
    if extra_state:
        trip_state.update(deepcopy(extra_state))
    TRIP_STATE[trip_id] = trip_state
    return trip_id, trip_state


def save_trip_snapshot(
    trip_id: str | None = None,
    trip_title: str | None = None,
) -> tuple[str, dict]:
    resolved_trip_id = trip_id or str(uuid4())
    existing_state = TRIP_STATE.get(resolved_trip_id, {})
    resolved_title = trip_title or existing_state.get("meta", {}).get("trip_title") or f"trip-{resolved_trip_id[:8]}"

    summary = {
        "trip_id": resolved_trip_id,
        "trip_title": resolved_title,
        "saved": True,
        "has_plan": "plan" in existing_state,
        "has_modify": "modify" in existing_state,
    }
    SAVED_TRIPS[resolved_trip_id] = summary

    state = TRIP_STATE.setdefault(
        resolved_trip_id,
        {
            "intent": Intent.MANAGE_TRIP.value,
            "meta": {"mcp": "fastmcp"},
        },
    )
    state_meta = dict(state.get("meta") or {})
    state_meta["trip_title"] = resolved_title
    state_meta["saved"] = True
    state_meta.setdefault("created_at", _now_iso())
    state_meta["updated_at"] = _now_iso()
    state["meta"] = state_meta

    return resolved_trip_id, summary


def get_saved_trip(trip_id: str | None) -> dict | None:
    if not trip_id:
        return None
    if trip_id in SAVED_TRIPS:
        return dict(SAVED_TRIPS[trip_id])
    state = TRIP_STATE.get(trip_id)
    if state is None:
        return None
    return {
        "trip_id": trip_id,
        "trip_title": state.get("meta", {}).get("trip_title") or f"trip-{trip_id[:8]}",
        "saved": bool(state.get("meta", {}).get("saved")),
        "has_plan": "plan" in state,
        "has_modify": "modify" in state,
    }


def list_saved_trips(scope: str = "saved") -> list[dict]:
    del scope
    return [dict(record) for record in reversed(list(SAVED_TRIPS.values()))]


def rename_saved_trip(trip_id: str | None, trip_title: str | None) -> dict | None:
    if not trip_id or not trip_title:
        return None
    record = get_saved_trip(trip_id)
    if record is None:
        return None
    record["trip_title"] = trip_title
    SAVED_TRIPS[trip_id] = dict(record)
    if trip_id in TRIP_STATE:
        state_meta = dict(TRIP_STATE[trip_id].get("meta") or {})
        state_meta["trip_title"] = trip_title
        TRIP_STATE[trip_id]["meta"] = state_meta
    return dict(record)


def delete_saved_trip(trip_id: str | None) -> bool:
    if not trip_id:
        return False
    removed = False
    if trip_id in SAVED_TRIPS:
        SAVED_TRIPS.pop(trip_id, None)
        removed = True
    if trip_id in TRIP_STATE:
        TRIP_STATE.pop(trip_id, None)
        removed = True
    return removed


def get_trip_state(trip_id: str | None) -> dict | None:
    if not trip_id:
        return None
    state = TRIP_STATE.get(trip_id)
    if state is None:
        return None
    return deepcopy(state)


def list_trip_states() -> list[tuple[str, dict]]:
    return list(TRIP_STATE.items())


def reset_trip_store() -> None:
    TRIP_STATE.clear()
    SAVED_TRIPS.clear()
