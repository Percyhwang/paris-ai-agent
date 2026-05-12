from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from parser_api.services.frontend_bridge_service import (
    add_budget_item,
    build_default_budget,
    build_weather,
    delete_budget_item,
    generate_diary,
    generate_trip,
    get_place,
    get_places,
    get_trip,
    list_trip_diaries,
    list_trip_reservations,
    list_trips,
    save_diary,
    save_reservation,
    update_budget,
)

web_api = APIRouter(prefix="/api")


def _ok(data: Any, message: str = "OK") -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "message": message,
        "error": None,
    }


def _fail(message: str, code: str = "BAD_REQUEST", status_code: int = 400, details: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "data": None,
            "message": message,
            "error": {
                "code": code,
                "details": details,
            },
        },
    )


@web_api.post("/trips/generate", response_model=None)
def api_generate_trip(payload: dict[str, Any]) -> Any:
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        return _fail("prompt is required", details={"field": "prompt"})
    try:
        return _ok(generate_trip(prompt))
    except ValueError as exc:
        return _fail(str(exc))


@web_api.get("/trips", response_model=None)
def api_list_trips() -> Any:
    return _ok(list_trips())


@web_api.get("/trips/{trip_id}", response_model=None)
def api_get_trip(trip_id: str) -> Any:
    trip = get_trip(trip_id)
    if trip is None:
        return _fail("trip not found", code="NOT_FOUND", status_code=404)
    return _ok(trip)


@web_api.get("/trips/{trip_id}/budget", response_model=None)
def api_get_budget(trip_id: str) -> Any:
    try:
        return _ok(build_default_budget(trip_id))
    except ValueError as exc:
        return _fail(str(exc), code="NOT_FOUND", status_code=404)


@web_api.put("/trips/{trip_id}/budget", response_model=None)
def api_update_budget(trip_id: str, payload: dict[str, Any]) -> Any:
    try:
        return _ok(update_budget(trip_id, payload))
    except ValueError as exc:
        return _fail(str(exc), code="NOT_FOUND", status_code=404)


@web_api.post("/trips/{trip_id}/budget/items", response_model=None)
def api_add_budget_item(trip_id: str, payload: dict[str, Any]) -> Any:
    try:
        return _ok(add_budget_item(trip_id, payload))
    except ValueError as exc:
        return _fail(str(exc), code="NOT_FOUND", status_code=404)


@web_api.delete("/trips/{trip_id}/budget/items/{item_id}", response_model=None)
def api_delete_budget_item(trip_id: str, item_id: str) -> Any:
    try:
        return _ok(delete_budget_item(trip_id, item_id))
    except ValueError as exc:
        return _fail(str(exc), code="NOT_FOUND", status_code=404)


@web_api.get("/trips/{trip_id}/diary", response_model=None)
def api_list_diary_entries(trip_id: str) -> Any:
    return _ok(list_trip_diaries(trip_id))


@web_api.post("/trips/{trip_id}/diary/generate", response_model=None)
def api_generate_diary(trip_id: str, payload: dict[str, Any]) -> Any:
    return _ok(generate_diary(trip_id, payload))


@web_api.post("/trips/{trip_id}/diary", response_model=None)
def api_create_diary_entry(trip_id: str, payload: dict[str, Any]) -> Any:
    return _ok(save_diary(trip_id, payload))


@web_api.get("/trips/{trip_id}/reservations", response_model=None)
def api_list_reservations(trip_id: str) -> Any:
    return _ok(list_trip_reservations(trip_id))


@web_api.post("/trips/{trip_id}/reservations", response_model=None)
def api_create_reservation(trip_id: str, payload: dict[str, Any]) -> Any:
    return _ok(save_reservation(trip_id, payload))


@web_api.get("/places", response_model=None)
def api_list_places(
    search: str = "",
    category: str = "",
    sort: str = Query(default="", pattern="^(|popular)$"),
) -> Any:
    return _ok(get_places(search=search, category=category, sort=sort))


@web_api.get("/places/{place_id}", response_model=None)
def api_get_place(place_id: str) -> Any:
    place = get_place(place_id)
    if place is None:
        return _fail("place not found", code="NOT_FOUND", status_code=404)
    return _ok(place)


@web_api.get("/weather/paris", response_model=None)
def api_get_current_weather() -> Any:
    payload = build_weather(1)
    today = payload["days"][0]
    current = {"city": "Paris", **today}
    return _ok(current)


@web_api.get("/weather/paris/forecast", response_model=None)
def api_get_weather_forecast(days: int = 7) -> Any:
    return _ok(build_weather(days))
