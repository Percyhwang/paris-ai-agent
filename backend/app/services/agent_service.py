from __future__ import annotations

import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from bson import ObjectId
from fastapi import HTTPException

from app.core.config import settings
from app.db.serializers import serialize_doc, serialize_many
from app.schemas.trips import TripAgentModifyRequest, TripGenerateRequest
from app.services.google_places_service import search_google_food_places
from app.services.planning_brief_service import (
    build_planning_brief,
    extract_planning_brief,
    mark_constraint_attempt,
    validate_planning_brief_compliance,
)
from app.services.place_repository_service import distance_meters, midpoint
from app.services.route_optimizer_service import attach_route_legs_to_days, optimize_trip_payload
from app.services.trip_service import ensure_trip_ownership, get_trip_detail

DEFAULT_COORDINATES: dict[str, dict[str, float]] = {
    "Eiffel Tower": {"lat": 48.8584, "lng": 2.2945},
    "Louvre Museum": {"lat": 48.8606, "lng": 2.3376},
    "Musee d'Orsay": {"lat": 48.86, "lng": 2.3266},
    "Notre-Dame": {"lat": 48.853, "lng": 2.3499},
    "Montmartre": {"lat": 48.8867, "lng": 2.3431},
    "Le Marais": {"lat": 48.8575, "lng": 2.358},
    "Luxembourg Gardens": {"lat": 48.8462, "lng": 2.3372},
    "Seine River": {"lat": 48.8583, "lng": 2.3375},
}

THEME_PLACE_POOL: dict[str, list[str]] = {
    "museum": ["Louvre Museum", "Musee d'Orsay"],
    "cafe": ["Saint-Germain cafe walk", "Le Marais cafe stop"],
    "shopping": ["Le Bon Marche", "Galeries Lafayette"],
    "night_view": ["Eiffel Tower", "Seine River"],
    "park": ["Luxembourg Gardens", "Tuileries Garden"],
}

DEFAULT_PLACE_ROTATION = [
    "Louvre Museum",
    "Notre-Dame",
    "Le Marais",
    "Montmartre",
    "Luxembourg Gardens",
    "Eiffel Tower",
]


async def generate_trip_payload(
    request: TripGenerateRequest,
    language: str = "ko",
    db: Any | None = None,
) -> dict[str, Any]:
    if settings.external_agent_api_url:
        payload = await _generate_with_external_agent(request, language=language)
        return await _optimize_payload_if_possible(db, payload, request, language)

    local_agent_response = _run_local_agent(request, language=language)
    if local_agent_response is not None:
        payload = _generated_payload_from_agent_response(local_agent_response, request, language=language)
        return await _optimize_payload_if_possible(db, payload, request, language)

    payload = _mock_trip_payload(request, language=language)
    return await _optimize_payload_if_possible(db, payload, request, language)


async def modify_trip_with_agent(
    db: Any,
    user_id: str,
    trip_id: str,
    request: TripAgentModifyRequest,
    language: str = "ko",
) -> dict[str, Any]:
    trip_doc = await ensure_trip_ownership(db, user_id, trip_id)
    day_docs = await db.itinerary_day.find({"trip_id": trip_id}).sort("day_number", 1).to_list(length=60)
    trip = serialize_doc(trip_doc)
    current_days = serialize_many(day_docs)

    agent_response = await _run_modify_agent(
        request=request,
        trip=trip,
        current_days=current_days,
        language=language,
    )
    modify_payload = _extract_modify_payload(agent_response)
    modify_payload["trip_id"] = str(modify_payload.get("trip_id") or trip_id)
    _fill_modify_operation_defaults(modify_payload, request.target_day, current_days)

    missing_fields = _missing_modify_fields(modify_payload)
    if missing_fields:
        raise HTTPException(
            status_code=422,
            detail=_copy(
                language,
                f"Agent needs more detail: {', '.join(missing_fields)}.",
                f"Agent가 추가 정보가 필요합니다: {', '.join(missing_fields)}.",
            ),
        )

    derived_state = _apply_modify_payload(
        trip=trip,
        current_days=current_days,
        modify_payload=modify_payload,
    )
    await _apply_google_food_replacements(derived_state, modify_payload, language=language)
    itinerary_days = list(derived_state.get("itinerary_days") or [])
    planning_brief = extract_planning_brief(trip) or build_planning_brief(
        plan=_plan_payload_from_trip(trip),
        trip=trip,
        intent="modify_trip",
    )
    await attach_route_legs_to_days(
        itinerary_days,
        prompt=request.prompt,
        style_tags=list(trip.get("style_tags") or []),
        language=language,
        planning_brief=planning_brief,
    )
    constraint_validation = validate_planning_brief_compliance(itinerary_days, planning_brief)
    derived_state["itinerary_days"] = itinerary_days
    await _persist_agent_modified_itinerary(
        db=db,
        user_id=user_id,
        trip_id=trip_id,
        itinerary_days=itinerary_days,
        route_summary=str(derived_state.get("route_summary") or trip.get("route_summary") or ""),
        planning_brief=planning_brief,
        constraint_validation=constraint_validation,
    )
    return await get_trip_detail(db, user_id, trip_id, language=language)


async def _optimize_payload_if_possible(
    db: Any | None,
    payload: dict[str, Any],
    request: TripGenerateRequest,
    language: str,
) -> dict[str, Any]:
    planning_brief = extract_planning_brief(payload) or build_planning_brief(
        plan=dict(payload.get("_plan_source") or {}),
        request=request,
        intent="create_trip",
    )
    current_payload = dict(payload)
    current_payload["planning_brief"] = planning_brief
    current_payload.setdefault("trip", {})["planning_brief"] = planning_brief
    plan_source = dict(current_payload.get("_plan_source") or {})
    max_replan_attempts = 2
    seen_violation_signatures: set[tuple[str, ...]] = set()

    for attempt in range(max_replan_attempts + 1):
        if db is not None:
            current_payload = await optimize_trip_payload(
                db,
                current_payload,
                prompt=request.prompt,
                language=language,
                planning_brief=planning_brief,
            )
        validation = validate_planning_brief_compliance(list(current_payload.get("itinerary_days") or []), planning_brief)
        current_payload["constraint_validation"] = validation
        current_payload["planning_brief"] = planning_brief
        current_payload.setdefault("trip", {})["planning_brief"] = planning_brief
        current_payload["trip"]["constraint_validation"] = validation
        requires_replan = _should_replan_validation(validation)
        if not requires_replan or not plan_source:
            if requires_replan:
                current_payload["trip"]["status"] = "needs_review"
            return current_payload

        violation_signature = _validation_signature(validation)
        if violation_signature in seen_violation_signatures or attempt >= max_replan_attempts:
            current_payload["trip"]["status"] = "needs_review"
            return current_payload
        seen_violation_signatures.add(violation_signature)

        reasons = [
            *(str(value) for value in validation.get("violated_constraints") or []),
            *(str(value) for value in validation.get("quality_violations") or []),
            *(str(value) for value in validation.get("warnings") or [] if "helper" in str(value)),
        ]
        reason = ", ".join(reasons or ["constraint_violation"])
        action = _replan_action(validation, planning_brief)
        previous_blueprints = [
            str(value)
            for value in (
                list(current_payload.get("selected_blueprints") or [])
                or [
                    str(day.get("blueprintArchetype") or day.get("dayArchetype") or "")
                    for day in current_payload.get("itinerary_days") or []
                    if str(day.get("blueprintArchetype") or day.get("dayArchetype") or "").strip()
                ]
            )
            if str(value).strip()
        ]
        planning_brief = mark_constraint_attempt(
            planning_brief,
            attempt + 1,
            reason,
            action,
            previous_blueprints=previous_blueprints,
        )
        current_payload = _generated_payload_from_plan(
            plan_source,
            request,
            language=language,
            planning_brief_override=planning_brief,
        )
    return current_payload


def _should_replan_validation(validation: dict[str, Any]) -> bool:
    if not isinstance(validation, dict):
        return False
    if not validation.get("is_valid"):
        return True
    if validation.get("quality_violations"):
        return True
    if any("helper" in str(value) for value in validation.get("warnings") or []):
        return True
    try:
        final_quality = float(validation.get("final_quality_score") or validation.get("score") or 0)
        story_flow = float(validation.get("story_flow_score") or 1)
        return final_quality < 0.82 or story_flow < 0.72
    except (TypeError, ValueError):
        return False


def _validation_signature(validation: dict[str, Any]) -> tuple[str, ...]:
    values = [
        *(str(value) for value in validation.get("violated_constraints") or []),
        *(str(value) for value in validation.get("quality_violations") or []),
        *(str(value) for value in validation.get("warnings") or [] if "helper" in str(value)),
        *(str(value) for value in validation.get("missing_must_include") or []),
        *(str(value) for value in validation.get("included_must_avoid") or []),
    ]
    return tuple(sorted(set(values)))


def _replan_action(validation: dict[str, Any], planning_brief: dict[str, Any]) -> str:
    missing = {str(value) for value in validation.get("missing_must_include") or [] if str(value)}
    violated = {str(value) for value in validation.get("violated_constraints") or [] if str(value)}
    quality = {str(value) for value in validation.get("quality_violations") or [] if str(value)}
    helper_warning = any("helper" in str(value) for value in validation.get("warnings") or [])
    has_eiffel = any("에펠" in value or "eiffel" in value.lower() for value in missing.union({str(value) for value in planning_brief.get("must_include") or []}))
    if has_eiffel and (planning_brief.get("night_view_required") or "time_slots" in violated):
        return "lock_eiffel_tower_to_night_slot"
    if quality or helper_warning or "story_flow" in violated:
        return "reduce_helper_blocks_and_rebuild"
    if planning_brief.get("night_view_required") or "time_slots" in violated:
        return "switch_to_evening_first_blueprint"
    return "strengthen_planning_brief_and_rebuild"


async def _generate_with_external_agent(request: TripGenerateRequest, language: str) -> dict[str, Any]:
    url = settings.external_agent_api_url
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(
                url,
                json=_external_agent_request_body(url, request, language=language),
                headers={"Accept-Language": language},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="External agent API failed") from exc

    return _normalize_agent_payload(response.json(), request, language=language)


def _run_local_agent(request: TripGenerateRequest, language: str) -> dict[str, Any] | None:
    _ensure_repo_root_on_path()
    try:
        from parser_api.schemas import AgentRunRequest
        from parser_api.services.agent_service import run_agent
    except ModuleNotFoundError:
        return None

    response = run_agent(
        AgentRunRequest(
            message=request.prompt,
            context=_agent_context_from_request(request, language=language),
        )
    )
    return response.model_dump()


async def _run_modify_agent(
    request: TripAgentModifyRequest,
    trip: dict[str, Any],
    current_days: list[dict[str, Any]],
    language: str,
) -> dict[str, Any]:
    if settings.external_agent_api_url:
        return await _run_external_modify_agent(request, trip, current_days, language)

    local_response = _run_local_modify_agent(request, trip, current_days, language)
    if local_response is not None:
        return local_response

    return _parse_modify_request_locally(request, trip, current_days, language)


async def _run_external_modify_agent(
    request: TripAgentModifyRequest,
    trip: dict[str, Any],
    current_days: list[dict[str, Any]],
    language: str,
) -> dict[str, Any]:
    url = settings.external_agent_api_url
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(
                url,
                json={
                    "message": request.prompt,
                    "context": _modify_agent_context(request, trip, current_days, language),
                },
                headers={"Accept-Language": language},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="External agent API failed") from exc

    payload = response.json()
    if isinstance(payload, dict) and isinstance(payload.get("success"), bool):
        if not payload["success"]:
            raise HTTPException(status_code=502, detail=str(payload.get("message") or "Agent API failed"))
        payload = dict(payload.get("data") or {})
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="Agent API returned an unsupported response shape")
    return payload


def _run_local_modify_agent(
    request: TripAgentModifyRequest,
    trip: dict[str, Any],
    current_days: list[dict[str, Any]],
    language: str,
) -> dict[str, Any] | None:
    _ensure_repo_root_on_path()
    try:
        from parser_api.intents import Intent
        from parser_api.services.orchestration_service import default_orchestrator
    except ModuleNotFoundError:
        return None

    response = default_orchestrator.run_for_intent(
        intent=Intent.MODIFY_PLAN,
        message=request.prompt,
        context=_modify_agent_context(request, trip, current_days, language),
    )
    return response.model_dump()


def _parse_modify_request_locally(
    request: TripAgentModifyRequest,
    trip: dict[str, Any],
    current_days: list[dict[str, Any]],
    language: str,
) -> dict[str, Any]:
    _ensure_repo_root_on_path()
    try:
        from parser_api.parsers.modify_plan.parser import parse_modify_plan
    except ModuleNotFoundError as exc:
        raise HTTPException(status_code=502, detail="Modify parser is unavailable") from exc

    payload = parse_modify_plan(
        request.prompt,
        _modify_agent_context(request, trip, current_days, language),
    )
    return {
        "status": "ASK" if payload.clarify.needed else "DONE",
        "intent": payload.intent,
        "trip_id": payload.trip_id or "",
        "data": {"modify": payload.model_dump(exclude={"clarify"})},
        "clarify": payload.clarify.model_dump(),
    }


def _modify_agent_context(
    request: TripAgentModifyRequest,
    trip: dict[str, Any],
    current_days: list[dict[str, Any]],
    language: str,
) -> dict[str, Any]:
    return {
        "source": "trip_plan_page",
        "language": language,
        "trip_id": trip.get("id"),
        "trip_title": trip.get("trip_title"),
        "target_day": request.target_day,
        "total_days": trip.get("total_days"),
        "style_tags": list(trip.get("style_tags") or []),
        "itinerary_days": _compact_itinerary_context(current_days),
    }


def _compact_itinerary_context(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact_days: list[dict[str, Any]] = []
    for day in days:
        compact_days.append(
            {
                "day_number": day.get("day_number"),
                "title": day.get("title"),
                "items": [
                    {
                        "time_slot": item.get("time_slot"),
                        "title": item.get("title"),
                        "place_name": (item.get("place") or {}).get("name"),
                    }
                    for item in day.get("items", [])
                    if isinstance(item, dict)
                ],
            }
        )
    return compact_days


def _extract_modify_payload(agent_response: dict[str, Any]) -> dict[str, Any]:
    status = str(agent_response.get("status") or "")
    if status == "ERROR":
        raise HTTPException(status_code=502, detail="Agent failed to modify the trip")

    data = dict(agent_response.get("data") or {})
    modify_payload = data.get("modify")
    if not isinstance(modify_payload, dict):
        bundle = data.get("bundle")
        if isinstance(bundle, dict):
            modify_payload = _extract_modify_from_bundle(bundle)

    if not isinstance(modify_payload, dict):
        raise HTTPException(status_code=502, detail="Agent did not return a modify payload")

    return dict(modify_payload)


def _extract_modify_from_bundle(bundle: dict[str, Any]) -> dict[str, Any] | None:
    for result in bundle.get("results") or []:
        if not isinstance(result, dict):
            continue
        data = result.get("data")
        if isinstance(data, dict) and isinstance(data.get("modify"), dict):
            return dict(data["modify"])
    return None


def _fill_modify_operation_defaults(
    modify_payload: dict[str, Any],
    default_day: int | None,
    current_days: list[dict[str, Any]],
) -> None:
    modify_payload["trip_id"] = str(modify_payload.get("trip_id") or "")
    operations = list(modify_payload.get("operations") or [])
    for operation in operations:
        if not isinstance(operation, dict):
            continue
        operation["target_slot"] = _normalize_agent_slot(operation.get("target_slot"))
        if isinstance(operation.get("swap_slots"), list):
            operation["swap_slots"] = [_normalize_agent_slot(slot) for slot in operation["swap_slots"]]

        if operation.get("target_day"):
            continue

        patch = operation.get("constraints_patch") if isinstance(operation.get("constraints_patch"), dict) else {}
        place_hint = operation.get("place_name") or patch.get("from_place") or patch.get("to_place")
        inferred_day = _find_day_containing_place(current_days, place_hint)
        if inferred_day is not None:
            operation["target_day"] = inferred_day
        elif default_day is not None:
            operation["target_day"] = default_day

    clarify = modify_payload.get("clarify")
    if isinstance(clarify, dict):
        missing = _missing_modify_fields(modify_payload)
        clarify["missing_fields"] = missing
        clarify["needed"] = bool(missing)


def _missing_modify_fields(modify_payload: dict[str, Any]) -> list[str]:
    missing_fields: list[str] = []
    if not modify_payload.get("trip_id"):
        missing_fields.append("trip_id")

    operations = [operation for operation in modify_payload.get("operations") or [] if isinstance(operation, dict)]
    if not operations:
        missing_fields.append("operations")

    for operation in operations:
        op = str(operation.get("op") or "")
        place_hint = operation.get("place_name")
        patch = operation.get("constraints_patch") if isinstance(operation.get("constraints_patch"), dict) else {}
        from_place = patch.get("from_place")
        if op in {"add", "swap", "move"} and not operation.get("target_day"):
            missing_fields.append("operations.target_day")
        if op in {"remove", "replace"} and not operation.get("target_day") and not (place_hint or from_place):
            missing_fields.append("operations.target_day")

    return list(dict.fromkeys(missing_fields))


def _apply_modify_payload(
    trip: dict[str, Any],
    current_days: list[dict[str, Any]],
    modify_payload: dict[str, Any],
) -> dict[str, Any]:
    _ensure_repo_root_on_path()
    try:
        from parser_api.services.place_catalog import apply_modifications, resolve_place
    except ModuleNotFoundError as exc:
        raise HTTPException(status_code=502, detail="Modify executor is unavailable") from exc

    derived_state = apply_modifications(
        plan_payload=_plan_payload_from_trip(trip),
        modify_payload=modify_payload,
        existing_itinerary_days=current_days,
        existing_route_summary=trip.get("route_summary"),
    )
    _enforce_direct_replacements(derived_state, modify_payload, resolve_place)
    return derived_state


def _enforce_direct_replacements(
    derived_state: dict[str, Any],
    modify_payload: dict[str, Any],
    resolve_place_fn: Any,
) -> None:
    itinerary_days = list(derived_state.get("itinerary_days") or [])
    changed = False

    for operation in modify_payload.get("operations") or []:
        if not isinstance(operation, dict) or operation.get("op") != "replace":
            continue

        day_number = operation.get("target_day")
        day = next((item for item in itinerary_days if item.get("day_number") == day_number), None)
        if not isinstance(day, dict):
            continue

        patch = operation.get("constraints_patch") if isinstance(operation.get("constraints_patch"), dict) else {}
        from_place = patch.get("from_place") or operation.get("place_name")
        to_place = patch.get("to_place") or operation.get("place_name")
        replacement = resolve_place_fn(to_place)
        items = list(day.get("items") or [])
        replace_index = _find_agent_item_index(items, from_place)
        if replace_index is None or replacement is None:
            continue

        previous = items[replace_index]
        slot = str(previous.get("time_slot") or operation.get("target_slot") or "afternoon")
        items[replace_index] = _agent_item_from_resolved_place(
            place=replacement,
            day_number=int(day_number or 1),
            slot=slot,
            item_index=replace_index + 1,
        )
        day["items"] = items
        day["route_summary"] = _agent_day_route_summary(items)
        changed = True

    if changed:
        selected_places = _agent_selected_places(itinerary_days)
        derived_state["selected_places"] = selected_places
        if selected_places:
            derived_state["route_summary"] = f"{', '.join(selected_places[:5])} 중심으로 Agent 수정 요청을 반영했습니다."


async def _apply_google_food_replacements(
    derived_state: dict[str, Any],
    modify_payload: dict[str, Any],
    *,
    language: str,
) -> None:
    itinerary_days = list(derived_state.get("itinerary_days") or [])
    changed = False

    for operation in modify_payload.get("operations") or []:
        if not isinstance(operation, dict) or operation.get("op") != "replace":
            continue

        patch = operation.get("constraints_patch") if isinstance(operation.get("constraints_patch"), dict) else {}
        cuisine = str(patch.get("cuisine") or "").strip().lower()
        if not cuisine:
            continue

        day_number = operation.get("target_day")
        day = next((item for item in itinerary_days if item.get("day_number") == day_number), None)
        if not isinstance(day, dict):
            continue

        items = list(day.get("items") or [])
        replace_index = _find_agent_item_index(items, patch.get("from_place") or operation.get("place_name"))
        if replace_index is None:
            replace_index = _find_agent_slot_item_index(items, _normalize_agent_slot(operation.get("target_slot")))
        if replace_index is None:
            continue

        anchor = _agent_food_search_anchor(items, replace_index)
        google_candidates = await search_google_food_places(cuisine=cuisine, center=anchor, language=language)
        selected = _choose_google_food_candidate(google_candidates, items=items, replace_index=replace_index)
        if not selected:
            continue

        previous = items[replace_index]
        slot = str(previous.get("time_slot") or operation.get("target_slot") or "lunch")
        items[replace_index] = _agent_item_from_google_place(
            place=selected,
            previous_item=previous,
            day_number=int(day_number or 1),
            slot=slot,
            item_index=replace_index + 1,
        )
        day["items"] = items
        day["route_summary"] = _agent_day_route_summary(items)
        changed = True

    if changed:
        selected_places = _agent_selected_places(itinerary_days)
        derived_state["selected_places"] = selected_places
        if selected_places:
            derived_state["route_summary"] = f"{', '.join(selected_places[:5])} 중심으로 Agent 수정 요청을 반영했습니다."


def _find_agent_slot_item_index(items: list[dict[str, Any]], target_slot: Any) -> int | None:
    if not target_slot:
        return None
    normalized_slot = _normalize_agent_slot(target_slot)
    return next((index for index, item in enumerate(items) if item.get("time_slot") == normalized_slot), None)


def _agent_food_search_anchor(items: list[dict[str, Any]], replace_index: int) -> dict[str, float]:
    previous_coordinates = _agent_item_coordinates(items[replace_index - 1]) if replace_index > 0 else None
    next_coordinates = _agent_item_coordinates(items[replace_index + 1]) if replace_index + 1 < len(items) else None
    if previous_coordinates and next_coordinates:
        return midpoint(previous_coordinates, next_coordinates)
    return previous_coordinates or next_coordinates or {"lat": 48.8566, "lng": 2.3522}


def _choose_google_food_candidate(
    candidates: list[dict[str, Any]],
    *,
    items: list[dict[str, Any]],
    replace_index: int,
) -> dict[str, Any] | None:
    used_names = {
        _simple_normalize(str((item.get("place") or {}).get("name") or item.get("title") or ""))
        for index, item in enumerate(items)
        if index != replace_index
    }
    available = [
        candidate
        for candidate in candidates
        if _simple_normalize(str(candidate.get("name") or "")) not in used_names
        and candidate.get("coordinates")
    ]
    if not available:
        return None

    return min(
        available,
        key=lambda candidate: (
            round(_candidate_agent_route_distance(candidate, items=items, replace_index=replace_index) / 100),
            -float(candidate.get("rating") or 0),
            -int(candidate.get("review_count") or 0),
            -float(candidate.get("popularity") or 0),
            str(candidate.get("name") or ""),
        ),
    )


def _candidate_agent_route_distance(
    candidate: dict[str, Any],
    *,
    items: list[dict[str, Any]],
    replace_index: int,
) -> int:
    coordinates = candidate.get("coordinates")
    if not isinstance(coordinates, dict):
        return 0
    anchors: list[dict[str, float]] = []
    previous_coordinates = _agent_item_coordinates(items[replace_index - 1]) if replace_index > 0 else None
    next_coordinates = _agent_item_coordinates(items[replace_index + 1]) if replace_index + 1 < len(items) else None
    if previous_coordinates:
        anchors.append(previous_coordinates)
    if next_coordinates:
        anchors.append(next_coordinates)
    return sum(distance_meters(coordinates, anchor) for anchor in anchors)


def _agent_item_coordinates(item: dict[str, Any]) -> dict[str, float] | None:
    coordinates = (item.get("place") or {}).get("coordinates")
    if not isinstance(coordinates, dict):
        return None
    lat = coordinates.get("lat")
    lng = coordinates.get("lng")
    if lat is None or lng is None:
        return None
    return {"lat": float(lat), "lng": float(lng)}


def _agent_item_from_google_place(
    *,
    place: dict[str, Any],
    previous_item: dict[str, Any],
    day_number: int,
    slot: str,
    item_index: int,
) -> dict[str, Any]:
    return {
        "id": f"{day_number}-{place['slug']}-{item_index}",
        "time_slot": slot,
        "start_time": str(previous_item.get("start_time") or _agent_slot_start_time(slot)),
        "title": place["name"],
        "place": {
            "place_id": place.get("google_place_id") or place.get("id") or place["slug"],
            "name": place["name"],
            "coordinates": dict(place["coordinates"]),
            "category": place.get("category") or "restaurant",
            "cuisine": place.get("cuisine"),
            "rating": place.get("rating"),
            "review_count": place.get("review_count"),
            "google_place_id": place.get("google_place_id"),
            "google_maps_uri": place.get("google_maps_uri"),
        },
        "description": place.get("short_description") or previous_item.get("description") or "",
        "estimated_duration": place.get("estimated_visit_duration") or previous_item.get("estimated_duration") or "1 hour",
        "area": previous_item.get("area"),
    }


def _find_agent_item_index(items: list[dict[str, Any]], place_hint: Any) -> int | None:
    if not place_hint:
        return None
    normalized_hint = _simple_normalize(str(place_hint))
    for index, item in enumerate(items):
        item_name = str((item.get("place") or {}).get("name") or item.get("title") or "")
        normalized_item = _simple_normalize(item_name)
        if normalized_hint and (
            normalized_hint == normalized_item
            or normalized_hint in normalized_item
            or normalized_item in normalized_hint
        ):
            return index
    return None


def _agent_item_from_resolved_place(
    *,
    place: dict[str, Any],
    day_number: int,
    slot: str,
    item_index: int,
) -> dict[str, Any]:
    return {
        "id": f"{day_number}-{place['slug']}-{item_index}",
        "time_slot": slot,
        "start_time": _agent_slot_start_time(slot),
        "title": place["name"],
        "place": {
            "place_id": place["slug"],
            "name": place["name"],
            "coordinates": dict(place["coordinates"]),
            "category": place["category"],
            "admission_fee": place.get("admission_fee"),
            "admission_fee_amount": place.get("admission_fee_amount"),
        },
        "description": place["short_description"],
        "estimated_duration": place["estimated_visit_duration"],
    }


def _agent_slot_start_time(slot: str) -> str:
    return {
        "morning": "09:00",
        "lunch": "12:30",
        "afternoon": "15:00",
        "evening": "19:00",
    }.get(slot, "15:00")


def _agent_day_route_summary(items: list[dict[str, Any]]) -> str:
    names = [str(item.get("title") or "") for item in items if item.get("title")]
    return f"{', '.join(names[:4])} 중심으로 Agent 수정 요청을 반영했습니다." if names else "Agent 수정 요청을 반영했습니다."


def _agent_selected_places(itinerary_days: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for day in itinerary_days:
        for item in day.get("items") or []:
            name = str((item.get("place") or {}).get("name") or item.get("title") or "").strip()
            if name:
                names.append(name)
    return list(dict.fromkeys(names))


def _plan_payload_from_trip(trip: dict[str, Any]) -> dict[str, Any]:
    planning_brief = extract_planning_brief(trip) or {}
    tags = list(
        dict.fromkeys(
            [
                *[str(tag) for tag in planning_brief.get("travel_style") or []],
                *[str(tag) for tag in trip.get("style_tags") or []],
            ]
        )
    )
    pace = str(planning_brief.get("pace") or "").lower()
    if pace not in {"slow", "normal", "fast"}:
        pace = "slow" if "slow" in tags or "여유" in tags else "fast" if "fast" in tags else "normal"
    budget_range = planning_brief.get("budget_range") if isinstance(planning_brief.get("budget_range"), dict) else {}
    return {
        "dates": {
            "start_date": _date_to_iso(trip.get("start_date")),
            "end_date": _date_to_iso(trip.get("end_date")),
            "days": trip.get("total_days"),
        },
        "destination": {"city": planning_brief.get("destination") or "Paris", "country": "FR"},
        "preferences": {
            "themes": tags,
            "must_include": list(planning_brief.get("must_include") or []),
            "must_avoid": list(planning_brief.get("must_avoid") or []),
            "travel_style": list(planning_brief.get("travel_style") or tags),
            "preferred_time_slots": list(planning_brief.get("preferred_time_slots") or []),
            "meal_preference": list(planning_brief.get("meal_preference") or []),
            "night_view_required": bool(planning_brief.get("night_view_required")),
        },
        "pace": {"level": pace},
        "budget": {
            "currency": budget_range.get("currency") or "EUR",
            "budget_total": budget_range.get("budget_total"),
            "budget_per_day": budget_range.get("budget_per_day"),
            "budget_mode": budget_range.get("budget_mode") or "normal",
        },
        "lodging": {"text": planning_brief.get("hotel_area_preference")},
        "mobility": {
            "travel_mode": planning_brief.get("transport_preference") or "both",
            "optimize": "min_time",
        },
        "planning_brief": planning_brief,
    }


async def _persist_agent_modified_itinerary(
    *,
    db: Any,
    user_id: str,
    trip_id: str,
    itinerary_days: list[dict[str, Any]],
    route_summary: str,
    planning_brief: dict[str, Any] | None = None,
    constraint_validation: dict[str, Any] | None = None,
) -> None:
    now = datetime.now(UTC)
    await db.itinerary_day.delete_many({"trip_id": trip_id})
    day_docs = []
    for day in itinerary_days:
        day_doc = dict(day)
        day_doc.pop("id", None)
        day_doc["trip_id"] = trip_id
        day_doc["user_id"] = user_id
        day_doc["date"] = _agent_date_to_datetime(day_doc.get("date"))
        day_doc["created_at"] = now
        day_doc["updated_at"] = now
        day_docs.append(day_doc)
    if day_docs:
        await db.itinerary_day.insert_many(day_docs)

    await db.trip_plans.update_one(
        {"_id": ObjectId(trip_id)},
        {
            "$set": {
                "route_summary": route_summary,
                "status": "modified",
                "planning_brief": planning_brief,
                "constraint_validation": constraint_validation,
                "updated_at": now,
            }
        },
    )


def _agent_date_to_datetime(value: date | datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _normalize_agent_slot(value: Any) -> Any:
    slot = str(value) if value is not None else value
    return {"dinner": "evening", "night": "evening"}.get(slot, slot)


def _find_day_containing_place(days: list[dict[str, Any]], place_hint: Any) -> int | None:
    if not place_hint:
        return None
    normalized_hint = _simple_normalize(str(place_hint))
    if not normalized_hint:
        return None

    for day in days:
        for item in day.get("items") or []:
            if not isinstance(item, dict):
                continue
            item_name = str((item.get("place") or {}).get("name") or item.get("title") or "")
            normalized_item_name = _simple_normalize(item_name)
            if normalized_hint in normalized_item_name or normalized_item_name in normalized_hint:
                try:
                    return int(day.get("day_number") or 0)
                except (TypeError, ValueError):
                    return None
    return None


def _simple_normalize(value: str) -> str:
    return "".join(char.lower() for char in value if char.isalnum())


def _ensure_repo_root_on_path() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    repo_root_path = str(repo_root)
    if repo_root_path not in sys.path:
        sys.path.append(repo_root_path)


def _external_agent_request_body(url: str, request: TripGenerateRequest, language: str) -> dict[str, Any]:
    path = urlparse(url).path.rstrip("/")
    if path.endswith("/agent/run"):
        return {
            "message": request.prompt,
            "context": _agent_context_from_request(request, language=language),
        }
    return request.model_dump(mode="json")


def _agent_context_from_request(request: TripGenerateRequest, language: str) -> dict[str, Any]:
    return {
        "source": "frontend",
        "language": language,
        "start_date": _date_to_iso(request.start_date),
        "end_date": _date_to_iso(request.end_date),
        "total_days": request.total_days,
        "style_tags": list(request.style_tags),
    }


def _normalize_agent_payload(
    raw_payload: dict[str, Any],
    request: TripGenerateRequest,
    language: str,
) -> dict[str, Any]:
    payload = raw_payload
    if isinstance(payload.get("success"), bool):
        if not payload["success"]:
            raise HTTPException(status_code=502, detail=str(payload.get("message") or "Agent API failed"))
        payload = dict(payload.get("data") or {})

    if "trip" in payload and "itinerary_days" in payload:
        return _normalize_generated_payload(payload, request, language=language)

    if "trip_title" in payload and "itinerary_days" in payload:
        return _generated_payload_from_frontend_trip(payload, request, language=language)

    if "status" in payload and "data" in payload:
        return _generated_payload_from_agent_response(payload, request, language=language)

    raise HTTPException(status_code=502, detail="Agent API returned an unsupported response shape")


def _normalize_generated_payload(
    payload: dict[str, Any],
    request: TripGenerateRequest,
    language: str,
) -> dict[str, Any]:
    trip = dict(payload.get("trip") or {})
    planning_brief = extract_planning_brief(payload) or extract_planning_brief({"trip": trip})
    constraint_validation = payload.get("constraint_validation") or trip.get("constraint_validation")
    trip.setdefault("trip_title", _title_from_prompt(request.prompt, _resolve_total_days(request, {}), language))
    trip.setdefault("prompt", request.prompt)
    trip.setdefault("total_days", _resolve_total_days(request, {}))
    trip.setdefault("style_tags", list(request.style_tags) or _infer_tags(request.prompt))
    trip.setdefault("status", "generated")
    trip.setdefault("route_summary", _copy(language, "Agent-generated Paris itinerary draft.", "Agent가 생성한 파리 일정 초안입니다."))
    normalized = {
        "trip": trip,
        "itinerary_days": list(payload.get("itinerary_days") or []),
        "budget": dict(payload.get("budget") or _budget_from_days(int(trip.get("total_days") or 1))),
    }
    if planning_brief:
        trip["planning_brief"] = planning_brief
        normalized["planning_brief"] = planning_brief
    if isinstance(constraint_validation, dict):
        trip["constraint_validation"] = constraint_validation
        normalized["constraint_validation"] = constraint_validation
    if isinstance(payload.get("_plan_source"), dict):
        normalized["_plan_source"] = dict(payload["_plan_source"])
    return normalized


def _generated_payload_from_frontend_trip(
    trip: dict[str, Any],
    request: TripGenerateRequest,
    language: str,
) -> dict[str, Any]:
    total_days = int(trip.get("total_days") or _resolve_total_days(request, {}))
    payload = {
        "trip": {
            "trip_title": trip.get("trip_title") or _title_from_prompt(request.prompt, total_days, language),
            "prompt": trip.get("prompt") or request.prompt,
            "start_date": trip.get("start_date"),
            "end_date": trip.get("end_date"),
            "total_days": total_days,
            "style_tags": list(trip.get("style_tags") or request.style_tags or _infer_tags(request.prompt)),
            "status": trip.get("status") or "generated",
            "route_summary": trip.get("route_summary") or _copy(
                language,
                "Agent-generated Paris itinerary draft.",
                "Agent가 생성한 파리 일정 초안입니다.",
            ),
        },
        "itinerary_days": list(trip.get("itinerary_days") or []),
        "budget": _budget_from_days(total_days),
    }
    planning_brief = extract_planning_brief({"trip": trip})
    if planning_brief:
        payload["planning_brief"] = planning_brief
        payload["trip"]["planning_brief"] = planning_brief
    if isinstance(trip.get("constraint_validation"), dict):
        payload["constraint_validation"] = dict(trip["constraint_validation"])
        payload["trip"]["constraint_validation"] = dict(trip["constraint_validation"])
    if isinstance(trip.get("_plan_source"), dict):
        payload["_plan_source"] = dict(trip["_plan_source"])
    return payload


def _generated_payload_from_agent_response(
    response: dict[str, Any],
    request: TripGenerateRequest,
    language: str,
) -> dict[str, Any]:
    status = str(response.get("status") or "")
    data = dict(response.get("data") or {})
    response_brief = data.get("planning_brief") if isinstance(data.get("planning_brief"), dict) else None
    if status == "ASK":
        plan = dict(data.get("plan") or {})
        payload = _generated_payload_from_plan(
            plan,
            request,
            language=language,
            planning_brief_override=response_brief or _extract_embedded_planning_brief(plan),
        )
        payload["trip"]["status"] = "needs_review"
        payload["trip"]["route_summary"] = (
            f"{payload['trip']['route_summary']} "
            f"{_copy(language, 'Agent asked for more detail, so this draft uses sensible defaults.', 'Agent가 추가 정보를 요청해 기본값으로 초안을 만들었습니다.')}"
        )
        return payload
    if status not in {"DONE", "PARTIAL"}:
        raise HTTPException(status_code=502, detail="Agent failed to generate a trip")

    plan = dict(data.get("plan") or {})
    embedded_brief = response_brief
    if not plan:
        bundle_plan = _extract_plan_from_bundle(data.get("bundle"))
        if bundle_plan:
            plan = bundle_plan
        embedded_brief = embedded_brief or _extract_planning_brief_from_bundle(data.get("bundle"))
    return _generated_payload_from_plan(
        plan,
        request,
        language=language,
        planning_brief_override=embedded_brief or _extract_embedded_planning_brief(plan),
    )


def _extract_plan_from_bundle(bundle: Any) -> dict[str, Any] | None:
    if not isinstance(bundle, dict):
        return None
    for result in bundle.get("results") or []:
        if not isinstance(result, dict):
            continue
        data = result.get("data") or {}
        plan = data.get("plan") if isinstance(data, dict) else None
        if isinstance(plan, dict):
            return plan
    return None


def _extract_planning_brief_from_bundle(bundle: Any) -> dict[str, Any] | None:
    if not isinstance(bundle, dict):
        return None
    for result in bundle.get("results") or []:
        if not isinstance(result, dict):
            continue
        data = result.get("data") or {}
        if isinstance(data, dict) and isinstance(data.get("planning_brief"), dict):
            return dict(data["planning_brief"])
    return None


def _extract_embedded_planning_brief(payload: dict[str, Any]) -> dict[str, Any] | None:
    brief = payload.get("_planning_brief")
    return dict(brief) if isinstance(brief, dict) else None


def _generated_payload_from_plan(
    plan: dict[str, Any],
    request: TripGenerateRequest,
    language: str,
    planning_brief_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    total_days = _resolve_total_days(request, plan)
    start, end = _resolve_dates(request, plan, total_days)
    themes = list(dict.fromkeys([*_plan_themes(plan), *request.style_tags, *_infer_tags(request.prompt)]))
    must_include = _plan_must_include(plan)
    planning_brief = planning_brief_override or build_planning_brief(
        plan=plan,
        request=request,
        intent="create_trip",
    )

    itinerary_bundle = _build_agent_itinerary_bundle(
        plan=plan,
        start=start,
        total_days=total_days,
        themes=themes,
        must_include=must_include,
        pace_level=_resolve_agent_pace_level(plan, request, themes),
        language=language,
        planning_brief=planning_brief,
    )
    itinerary_days = list(itinerary_bundle.get("itinerary_days") or [])
    selected_blueprints = list(itinerary_bundle.get("selected_blueprints") or [])
    route_summary = str(itinerary_bundle.get("route_summary") or _route_summary_from_plan(plan, language))

    tags = list(dict.fromkeys([*request.style_tags, *themes, *_infer_tags(request.prompt), *_mobility_tags(plan)]))
    return {
        "trip": {
            "trip_title": _title_from_prompt(request.prompt, total_days, language),
            "prompt": request.prompt,
            "start_date": start,
            "end_date": end,
            "total_days": total_days,
            "style_tags": tags or _infer_tags(request.prompt),
            "status": "generated",
            "route_summary": route_summary,
            "planning_brief": planning_brief,
        },
        "itinerary_days": itinerary_days,
        "budget": _budget_from_days(total_days, plan),
        "planning_brief": planning_brief,
        "selected_blueprints": selected_blueprints,
        "_plan_source": dict(plan),
    }


def _build_agent_day(
    *,
    day_number: int,
    day_date: date,
    total_days: int,
    themes: list[str],
    must_include: list[str],
    plan: dict[str, Any],
    language: str,
) -> dict[str, Any]:
    morning_place = _select_place(day_number - 1, themes, must_include)
    afternoon_place = _select_place(day_number, themes, must_include)
    evening_place = _select_evening_place(day_number, themes)

    evening_description = (
        _copy(language, "End the trip with a memorable Paris view.", "기억에 남을 파리 전망으로 여행을 마무리합니다.")
        if day_number == total_days
        else _copy(language, "Close the day with a slower evening stop.", "느긋한 저녁 코스로 하루를 정리합니다.")
    )

    return {
        "day_number": day_number,
        "date": day_date,
        "title": _copy(language, f"Day {day_number} Paris plan", f"파리 {day_number}일차 일정"),
        "route_summary": _route_summary_from_plan(plan, language),
        "items": [
            _itinerary_item(
                "morning",
                "09:30",
                morning_place,
                _copy(language, "Start with a focused Paris highlight.", "파리의 핵심 명소로 하루를 시작합니다."),
            ),
            _itinerary_item(
                "lunch",
                "12:30",
                "Le Marais cafe stop",
                _copy(language, "Keep lunch close to the walking route.", "도보 동선 가까운 곳에서 점심을 잡습니다."),
            ),
            _itinerary_item(
                "afternoon",
                "15:00",
                afternoon_place,
                _copy(language, "Spend the afternoon around the selected theme.", "선택한 취향을 중심으로 오후 일정을 구성합니다."),
            ),
            _itinerary_item("evening", "19:30", evening_place, evening_description),
        ],
    }


def _build_agent_itinerary_bundle(
    *,
    plan: dict[str, Any],
    start: date,
    total_days: int,
    themes: list[str],
    must_include: list[str],
    pace_level: str,
    language: str,
    planning_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _ensure_repo_root_on_path()
    try:
        from parser_api.services.place_catalog import build_itinerary
    except ModuleNotFoundError:
        return {
            "itinerary_days": [
                _build_agent_day(
                    day_number=day_number,
                    day_date=start + timedelta(days=day_number - 1),
                    total_days=total_days,
                    themes=themes,
                    must_include=must_include,
                    plan=plan,
                    language=language,
                )
                for day_number in range(1, total_days + 1)
            ],
            "route_summary": _route_summary_from_plan(plan, language),
            "selected_blueprints": [],
        }

    payload = {
        "dates": {
            "start_date": start.isoformat(),
            "days": total_days,
        },
        "preferences": {
            "themes": themes,
            "must_include": must_include,
            "must_avoid": list(((plan.get("preferences") or {}).get("must_avoid") or [])),
            "travel_style": _plan_preference_list(plan, "travel_style"),
            "preferred_time_slots": _plan_preference_list(plan, "preferred_time_slots"),
            "meal_preference": _plan_preference_list(plan, "meal_preference"),
            "night_view_required": _plan_night_view_required(plan, themes),
        },
        "party": plan.get("party") or {},
        "budget": plan.get("budget") or {},
        "pace": {"level": pace_level},
        "mobility": plan.get("mobility") or {"travel_mode": "both", "optimize": "min_time"},
        "planning_brief": planning_brief or {},
    }
    return dict(build_itinerary(payload) or {})


def _resolve_agent_pace_level(plan: dict[str, Any], request: TripGenerateRequest, themes: list[str]) -> str:
    pace = plan.get("pace") if isinstance(plan.get("pace"), dict) else {}
    plan_level = str(pace.get("level") or "").lower()
    signals = " ".join(
        [
            request.prompt.lower(),
            *[str(tag).lower() for tag in request.style_tags],
            *[str(theme).lower() for theme in themes],
            *[str(tag).lower() for tag in _infer_tags(request.prompt)],
        ]
    )
    slow_tokens = (
        "slow",
        "relax",
        "relaxed",
        "healing",
        "\ud790\ub9c1",
        "\uc5ec\uc720",
        "\ud734\uc2dd",
        "\ub290\uae0b",
        "\ucc9c\ucc9c\ud788",
        "\uc26c\uc5c4",
    )
    fast_tokens = (
        "fast",
        "packed",
        "dense",
        "busy",
        "\uc54c\ucc28",
        "\ub9ce\uc774",
        "\ud0c0\uc774\ud2b8",
        "\ube61\ube61",
    )
    if any(token in signals for token in slow_tokens):
        return "slow"
    if plan_level in {"slow", "fast"}:
        return plan_level
    if any(token in signals for token in fast_tokens):
        return "fast"
    if plan_level == "normal":
        return "normal"
    return "normal"


def _itinerary_item(slot: str, start_time: str, place_name: str, description: str) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "time_slot": slot,
        "start_time": start_time,
        "title": place_name,
        "place": {
            "name": place_name,
            "category": _category_for_place(place_name),
            "coordinates": DEFAULT_COORDINATES.get(place_name),
        },
        "description": description,
        "estimated_duration": "1-2 hours",
    }


def _select_place(index: int, themes: list[str], must_include: list[str]) -> str:
    if must_include:
        return must_include[index % len(must_include)]
    for theme in themes:
        places = THEME_PLACE_POOL.get(theme)
        if places:
            return places[index % len(places)]
    return DEFAULT_PLACE_ROTATION[index % len(DEFAULT_PLACE_ROTATION)]


def _select_evening_place(index: int, themes: list[str]) -> str:
    if "night_view" in themes:
        return THEME_PLACE_POOL["night_view"][index % len(THEME_PLACE_POOL["night_view"])]
    return ["Seine River", "Eiffel Tower", "Montmartre"][index % 3]


def _category_for_place(place_name: str) -> str:
    lowered = place_name.lower()
    if "museum" in lowered or "orsay" in lowered or "louvre" in lowered:
        return "museum"
    if "cafe" in lowered:
        return "cafe"
    if "garden" in lowered or "park" in lowered:
        return "park"
    if "marche" in lowered or "lafayette" in lowered:
        return "shopping"
    return "landmark"


def _plan_themes(plan: dict[str, Any]) -> list[str]:
    preferences = plan.get("preferences") if isinstance(plan.get("preferences"), dict) else {}
    themes = preferences.get("themes") if isinstance(preferences, dict) else []
    if isinstance(themes, list):
        return [str(theme) for theme in themes if theme]
    return []


def _plan_preference_list(plan: dict[str, Any], field_name: str) -> list[str]:
    preferences = plan.get("preferences") if isinstance(plan.get("preferences"), dict) else {}
    values = preferences.get(field_name) if isinstance(preferences, dict) else []
    if isinstance(values, list):
        return [str(value) for value in values if value]
    return []


def _plan_must_include(plan: dict[str, Any]) -> list[str]:
    preferences = plan.get("preferences") if isinstance(plan.get("preferences"), dict) else {}
    must_include = preferences.get("must_include") if isinstance(preferences, dict) else []
    if isinstance(must_include, list):
        return [str(place) for place in must_include if place]
    return []


def _plan_night_view_required(plan: dict[str, Any], themes: list[str]) -> bool:
    preferences = plan.get("preferences") if isinstance(plan.get("preferences"), dict) else {}
    flag = preferences.get("night_view_required") if isinstance(preferences, dict) else False
    return bool(flag) or "night_view" in themes


def _mobility_tags(plan: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    for section_name, field_name in (("pace", "level"), ("mobility", "travel_mode")):
        section = plan.get(section_name)
        if isinstance(section, dict) and section.get(field_name):
            tags.append(str(section[field_name]))
    return tags


def _route_summary_from_plan(plan: dict[str, Any], language: str) -> str:
    mobility = plan.get("mobility") if isinstance(plan.get("mobility"), dict) else {}
    pace = plan.get("pace") if isinstance(plan.get("pace"), dict) else {}
    travel_mode = mobility.get("travel_mode") or "walk/transit"
    pace_level = pace.get("level") or "balanced"
    return _copy(
        language,
        f"Agent draft optimized for {travel_mode} movement with a {pace_level} pace.",
        f"{travel_mode} 이동과 {pace_level} 속도에 맞춘 Agent 일정 초안입니다.",
    )


def _budget_from_days(total_days: int, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    plan_budget = plan.get("budget") if isinstance(plan, dict) and isinstance(plan.get("budget"), dict) else {}
    budget_total = int(plan_budget.get("budget_total") or 0)
    grand_total = budget_total or total_days * 180
    return {
        "attraction_total": max(0, grand_total // 5),
        "hotel_total": max(0, (grand_total * 45) // 100),
        "custom_expenses": [],
        "currency": plan_budget.get("currency") or "EUR",
    }


def _resolve_total_days(request: TripGenerateRequest, plan: dict[str, Any]) -> int:
    dates = plan.get("dates") if isinstance(plan.get("dates"), dict) else {}
    return int(request.total_days or dates.get("days") or _infer_days(request.prompt) or 3)


def _resolve_dates(request: TripGenerateRequest, plan: dict[str, Any], total_days: int) -> tuple[date, date]:
    dates = plan.get("dates") if isinstance(plan.get("dates"), dict) else {}
    start = request.start_date or _parse_iso_date(dates.get("start_date")) or (date.today() + timedelta(days=45))
    end = request.end_date or _parse_iso_date(dates.get("end_date")) or (start + timedelta(days=total_days - 1))
    return start, end


def _parse_iso_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _date_to_iso(value: date | str | None) -> str | None:
    if isinstance(value, date):
        return value.isoformat()
    return value


def _fallback_plan_from_request(request: TripGenerateRequest) -> dict[str, Any]:
    total_days = request.total_days or _infer_days(request.prompt) or 3
    start = request.start_date or (date.today() + timedelta(days=45))
    tags = list(dict.fromkeys(request.style_tags or _infer_tags(request.prompt)))
    night_view_required = "night_view" in tags
    return {
        "dates": {
            "start_date": start.isoformat(),
            "days": total_days,
        },
        "preferences": {
            "themes": tags,
            "must_include": [],
            "must_avoid": [],
            "travel_style": tags,
            "preferred_time_slots": ["evening", "night"] if night_view_required else [],
            "meal_preference": ["cafe"] if "cafe" in tags or "foodie" in tags else [],
            "night_view_required": night_view_required,
        },
        "pace": {
            "level": "slow" if any(tag in {"slow", "relax", "relaxed", "healing", "여유", "휴식"} for tag in tags) else "normal"
        },
        "mobility": {"travel_mode": "both", "optimize": "min_time"},
    }


def _mock_trip_payload(request: TripGenerateRequest, language: str) -> dict[str, Any]:
    payload = _generated_payload_from_plan(_fallback_plan_from_request(request), request, language=language)
    fallback_note = _copy(
        language,
        "Paris itinerary draft generated from the local fallback planner.",
        "로컬 fallback planner로 생성한 파리 일정 초안입니다.",
    )
    existing_summary = str(payload["trip"].get("route_summary") or "").strip()
    payload["trip"]["route_summary"] = f"{existing_summary} {fallback_note}".strip()
    return payload


def _infer_days(prompt: str) -> int | None:
    lowered = prompt.lower()
    for days in range(1, 15):
        if f"{days} nights" in lowered or f"{days}박" in prompt:
            return days + 1
        if f"{days} days" in lowered or f"{days}-day" in lowered or f"{days}일" in prompt:
            return days
    return None


def _infer_tags(prompt: str) -> list[str]:
    lowered = prompt.lower()
    keyword_map = {
        "museum": "museum",
        "louvre": "museum",
        "cafe": "cafe",
        "shopping": "shopping",
        "night": "night_view",
        "view": "night_view",
        "park": "park",
        "walking": "walk",
        "미술": "museum",
        "박물관": "museum",
        "카페": "cafe",
        "쇼핑": "shopping",
        "야경": "night_view",
        "공원": "park",
    }
    tags = [tag for keyword, tag in keyword_map.items() if keyword in lowered or keyword in prompt]
    return list(dict.fromkeys(tags)) or ["classic", "balanced"]


def _title_from_prompt(prompt: str, total_days: int, language: str) -> str:
    tags = _infer_tags(prompt)
    if language == "en":
        if "museum" in tags:
            return f"{total_days}-Day Paris Museum Trip"
        if "night_view" in tags:
            return f"{total_days}-Day Paris Night-View Trip"
        if "cafe" in tags:
            return f"{total_days}-Day Paris Cafe Trip"
        return f"{total_days}-Day Paris Trip"

    if "museum" in tags:
        return f"파리 {total_days}일 미술관 여행"
    if "night_view" in tags:
        return f"파리 {total_days}일 야경 여행"
    if "cafe" in tags:
        return f"파리 {total_days}일 카페 여행"
    return f"파리 {total_days}일 여행"


def _copy(language: str, en: str, ko: str) -> str:
    return en if language == "en" else ko
