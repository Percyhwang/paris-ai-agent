from __future__ import annotations

from typing import Any

from parser_api.intents import Intent
from parser_api.mcp_servers.common import build_server, build_tool_response
from parser_api.mcp_servers.place_catalog_server import generate_itinerary, update_itinerary
from parser_api.schemas import (
    CreatePlanPayload,
    ManageTripPayload,
    ModifyPlanPayload,
    TripDiaryPayload,
)
from parser_api.services.planning_brief_service import build_unified_planning_brief
from parser_api.services.trip_store import (
    delete_saved_trip,
    get_saved_trip,
    get_trip_state,
    list_saved_trips,
    rename_saved_trip,
    save_create_plan_trip,
    save_modify_plan_trip,
    save_trip_snapshot,
)

SERVICE_NAME = "planning-service"
mcp = build_server(SERVICE_NAME)


def _render_diary_entry(payload: TripDiaryPayload) -> str:
    day_label = f"{payload.target_day}일차" if payload.target_day else "이번 여행"
    highlight_text = ", ".join(payload.highlights) if payload.highlights else "여행지"
    note_text = f" 메모: {payload.notes}" if payload.notes else ""
    tone_prefix = {
        "casual": "편안하게",
        "emotional": "감성적으로",
        "informative": "정보 중심으로",
        "blog": "블로그 스타일로",
    }[payload.tone]
    return f"{tone_prefix} 정리한 {day_label} 기록입니다. 주요 장소는 {highlight_text}.{note_text}".strip()


def _resolve_trip_id(payload: ManageTripPayload, context: dict[str, Any] | None) -> str:
    context_trip_id = str((context or {}).get("trip_id") or "")
    return str(payload.trip_id or context_trip_id or "")


@mcp.tool
def create_plan(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    validated = CreatePlanPayload.model_validate(payload)
    planning_brief = build_unified_planning_brief(Intent.CREATE_PLAN, validated, context)
    derived_state = generate_itinerary({**validated.model_dump(), "planning_brief": planning_brief or {}})
    if planning_brief:
        derived_state["planning_brief"] = planning_brief
    trip_id, trip_state = save_create_plan_trip(
        validated.model_dump(),
        meta={
            "mcp": "fastmcp",
            "server": SERVICE_NAME,
            "tool": "create_plan",
        },
        extra_state=derived_state,
    )
    return {"trip_id": trip_id, "data": trip_state}


@mcp.tool
def modify_plan(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    validated = ModifyPlanPayload.model_validate(payload)
    if not validated.trip_id and context and context.get("trip_id"):
        validated.trip_id = str(context["trip_id"])
    planning_brief = build_unified_planning_brief(Intent.MODIFY_PLAN, validated, context)

    existing_state = get_trip_state(validated.trip_id) if validated.trip_id else None
    derived_state: dict[str, Any] | None = {"planning_brief": planning_brief} if planning_brief else None
    if existing_state and existing_state.get("plan"):
        derived_state = update_itinerary(
            plan_payload=dict(existing_state.get("plan") or {}),
            modify_payload=validated.model_dump(),
            existing_itinerary_days=list(existing_state.get("itinerary_days") or []),
            existing_route_summary=str(existing_state.get("route_summary") or ""),
        )
        if planning_brief:
            derived_state["planning_brief"] = planning_brief

    trip_id, trip_state = save_modify_plan_trip(
        validated.model_dump(),
        meta={
            "mcp": "fastmcp",
            "server": SERVICE_NAME,
            "tool": "modify_plan",
        },
        extra_state=derived_state,
    )
    return {"trip_id": trip_id, "data": trip_state}


@mcp.tool
def manage_trip(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    validated = ManageTripPayload.model_validate(payload)
    resolved_trip_id = _resolve_trip_id(validated, context)

    payload_extras: dict[str, Any] = {}
    trip_id = resolved_trip_id

    if validated.operation == "save":
        trip_id, saved_trip = save_trip_snapshot(
            trip_id=resolved_trip_id or None,
            trip_title=validated.trip_title,
        )
        payload_extras["saved_trip"] = saved_trip
    elif validated.operation == "retrieve":
        record = get_saved_trip(resolved_trip_id)
        payload_extras["saved_trip"] = record
        payload_extras["found"] = record is not None
    elif validated.operation == "list":
        payload_extras["saved_trips"] = list_saved_trips(validated.scope)
    elif validated.operation == "rename":
        renamed = rename_saved_trip(resolved_trip_id, validated.trip_title)
        payload_extras["saved_trip"] = renamed
        payload_extras["found"] = renamed is not None
    elif validated.operation == "delete":
        deleted = delete_saved_trip(resolved_trip_id)
        payload_extras["deleted"] = deleted

    return build_tool_response(
        intent=Intent.MANAGE_TRIP,
        data_key="manage_trip",
        payload_dict=validated.model_dump(),
        service=SERVICE_NAME,
        tool="manage_trip",
        trip_id=trip_id,
        payload_extras=payload_extras,
    )


@mcp.tool
def trip_diary(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    validated = TripDiaryPayload.model_validate(payload)
    if not validated.trip_id and context and context.get("trip_id"):
        validated.trip_id = str(context["trip_id"])
    return build_tool_response(
        intent=Intent.TRIP_DIARY,
        data_key="trip_diary",
        payload_dict=validated.model_dump(),
        service=SERVICE_NAME,
        tool="trip_diary",
        trip_id=validated.trip_id or "",
        payload_extras={
            "generated_entry": _render_diary_entry(validated),
        },
    )


if __name__ == "__main__":
    mcp.run()
