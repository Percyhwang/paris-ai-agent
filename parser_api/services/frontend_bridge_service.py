from __future__ import annotations

from typing import Any
from uuid import uuid4

from parser_api.schemas import AgentRunRequest
from parser_api.services.agent_service import run_agent
from parser_api.services.frontend_store import (
    create_diary_entry,
    create_reservation,
    get_budget_state,
    list_diary_entries,
    list_reservations,
    set_budget_state,
)
from parser_api.services.place_catalog import resolve_place, search_places
from parser_api.services.trip_store import get_trip_state, list_trip_states


def _trip_title_from_state(trip_id: str, state: dict[str, Any]) -> str:
    meta = state.get("meta") or {}
    if meta.get("trip_title"):
        return str(meta["trip_title"])

    plan = state.get("plan") or {}
    destination = plan.get("destination", {}).get("city") or "Paris"
    days = plan.get("dates", {}).get("days")
    if days:
        return f"{destination} {days}일 여행"
    return f"{destination} 여행"


def _style_tags_from_state(state: dict[str, Any]) -> list[str]:
    plan = state.get("plan") or {}
    preferences = plan.get("preferences") or {}
    pace = plan.get("pace", {}).get("level")
    mobility = plan.get("mobility", {}).get("travel_mode")
    tags = list(preferences.get("themes") or [])
    if pace:
        tags.append(str(pace))
    if mobility:
        tags.append(str(mobility))
    if state.get("modify", {}).get("operations"):
        tags.append("modified")
    return list(dict.fromkeys(tag for tag in tags if tag))


def _route_summary_from_state(state: dict[str, Any]) -> str:
    if state.get("route_summary"):
        return str(state["route_summary"])

    plan = state.get("plan") or {}
    mobility = plan.get("mobility", {})
    pace = plan.get("pace", {})
    travel_mode = mobility.get("travel_mode", "both")
    optimize = mobility.get("optimize", "min_time")
    pace_level = pace.get("level", "normal")
    return f"{travel_mode} 이동, {optimize} 기준, {pace_level} 템포로 구성한 요청 요약입니다."


def _place_coordinates(name: str) -> dict[str, float] | None:
    place = resolve_place(name)
    if not place:
        return None
    return dict(place["coordinates"])


def _build_operation_item(operation: dict[str, Any], index: int) -> dict[str, Any]:
    constraints_patch = operation.get("constraints_patch") or {}
    place_name = operation.get("place_name") or constraints_patch.get("to_place") or constraints_patch.get("from_place") or "파리 스팟"
    description = f"{operation.get('op', 'update')} 요청을 반영한 변경 포인트입니다."
    return {
        "id": f"op-{index}",
        "time_slot": operation.get("target_slot") or "afternoon",
        "start_time": "14:00",
        "title": f"{place_name} 변경",
        "place": {
            "place_id": None,
            "name": place_name,
            "coordinates": _place_coordinates(place_name),
            "category": "agent_update",
        },
        "description": description,
        "estimated_duration": "1-2시간",
    }


def _build_default_item(name: str, slot: str, start_time: str) -> dict[str, Any]:
    return {
        "id": f"{slot}-{name}",
        "time_slot": slot,
        "start_time": start_time,
        "title": name,
        "place": {
            "place_id": None,
            "name": name,
            "coordinates": _place_coordinates(name),
            "category": "landmark",
        },
        "description": f"{name} 중심으로 동선을 검토할 수 있는 기본 제안입니다.",
        "estimated_duration": "1-2시간",
    }


def _build_itinerary_days(state: dict[str, Any]) -> list[dict[str, Any]]:
    stored_days = state.get("itinerary_days")
    if isinstance(stored_days, list) and stored_days:
        return [dict(day) for day in stored_days]

    plan = state.get("plan") or {}
    modify = state.get("modify") or {}
    total_days = int(plan.get("dates", {}).get("days") or 1)
    must_include = list(plan.get("preferences", {}).get("must_include") or [])
    themes = list(plan.get("preferences", {}).get("themes") or [])
    operations = list(modify.get("operations") or [])
    highlights = must_include or ["에펠탑", "루브르", "오르세"]
    fallback_name = "파리 산책" if "night_view" not in themes else "센강 야경 산책"

    itinerary_days: list[dict[str, Any]] = []
    for day_number in range(1, total_days + 1):
        day_items: list[dict[str, Any]] = []
        highlight_name = highlights[(day_number - 1) % len(highlights)] if highlights else fallback_name
        day_items.append(_build_default_item(highlight_name, "morning", "09:00"))

        if "cafe" in themes:
            day_items.append(_build_default_item("감성 카페 탐방", "afternoon", "14:00"))
        elif "shopping" in themes:
            day_items.append(_build_default_item("쇼핑 거리 산책", "afternoon", "14:00"))
        else:
            day_items.append(_build_default_item(fallback_name, "afternoon", "14:00"))

        for index, operation in enumerate(operations, start=1):
            if int(operation.get("target_day") or 0) == day_number:
                day_items.append(_build_operation_item(operation, index))

        itinerary_days.append(
            {
                "id": f"day-{day_number}",
                "day_number": day_number,
                "date": None,
                "title": f"Day {day_number}",
                "items": day_items,
                "route_summary": _route_summary_from_state(state),
            }
        )
    return itinerary_days


def build_trip_payload(trip_id: str, state: dict[str, Any]) -> dict[str, Any]:
    plan = state.get("plan") or {}
    meta = state.get("meta") or {}
    return {
        "id": trip_id,
        "user_id": "local-demo-user",
        "trip_title": _trip_title_from_state(trip_id, state),
        "prompt": meta.get("source_message"),
        "start_date": plan.get("dates", {}).get("start_date"),
        "end_date": plan.get("dates", {}).get("end_date"),
        "total_days": int(plan.get("dates", {}).get("days") or 1),
        "style_tags": _style_tags_from_state(state),
        "status": "draft",
        "itinerary_days": _build_itinerary_days(state),
        "route_summary": _route_summary_from_state(state),
        "created_at": meta.get("created_at"),
        "updated_at": meta.get("updated_at"),
    }


def list_trips() -> list[dict[str, Any]]:
    trips: list[dict[str, Any]] = []
    for trip_id, state in list_trip_states():
        if "plan" not in state and "modify" not in state:
            continue
        trips.append(build_trip_payload(trip_id, state))
    trips.sort(key=lambda trip: trip.get("updated_at") or "", reverse=True)
    return trips


def get_trip(trip_id: str) -> dict[str, Any] | None:
    state = get_trip_state(trip_id)
    if state is None:
        return None
    return build_trip_payload(trip_id, state)


def generate_trip(prompt: str) -> dict[str, Any]:
    response = run_agent(AgentRunRequest(message=prompt, context={}))
    if response.status not in {"DONE", "PARTIAL"}:
        missing = ", ".join(response.clarify.missing_fields) or "요청 정보"
        raise ValueError(f"여행 계획을 만들기 전에 {missing} 정보를 더 알려주세요.")
    if not response.trip_id:
        raise ValueError("여행 계획이 생성되지 않았습니다.")
    trip = get_trip(response.trip_id)
    if trip is None:
        raise ValueError("생성된 여행 계획을 불러오지 못했습니다.")
    return trip


def build_default_budget(trip_id: str) -> dict[str, Any]:
    trip = get_trip(trip_id)
    if trip is None:
        raise ValueError("여행 계획을 찾을 수 없습니다.")

    budget_state = get_budget_state(trip_id)
    if budget_state is not None:
        return budget_state

    days = max(1, int(trip.get("total_days") or 1))
    prompt = f"파리 {days}일 여행 예산 계산해줘. 호텔, 식비, 교통비 포함해줘."
    response = run_agent(AgentRunRequest(message=prompt, context={}))
    estimate = (
        response.data.get("budget_estimate", {}).get("estimate_total")
        if response.status in {"DONE", "PARTIAL"}
        else None
    )
    grand_total = int(estimate or (days * 180000))
    budget_payload = {
        "id": f"budget-{trip_id}",
        "trip_id": trip_id,
        "attraction_total": max(0, grand_total // 5),
        "hotel_total": max(0, (grand_total * 45) // 100),
        "custom_expenses": [],
        "grand_total": grand_total,
        "currency": "EUR",
    }
    return set_budget_state(trip_id, budget_payload)


def update_budget(trip_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    current = build_default_budget(trip_id)
    merged = dict(current)
    merged.update(payload)
    merged["custom_expenses"] = list(current.get("custom_expenses") or [])
    merged["grand_total"] = int(merged.get("attraction_total", 0)) + int(merged.get("hotel_total", 0))
    for item in merged["custom_expenses"]:
        merged["grand_total"] += int(item.get("amount") or 0)
    return set_budget_state(trip_id, merged)


def add_budget_item(trip_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    current = build_default_budget(trip_id)
    item = {"id": str(uuid4()), **payload}
    items = list(current.get("custom_expenses") or [])
    items.append(item)
    current["custom_expenses"] = items
    current["grand_total"] = int(current.get("attraction_total", 0)) + int(current.get("hotel_total", 0))
    for current_item in items:
        current["grand_total"] += int(current_item.get("amount") or 0)
    return set_budget_state(trip_id, current)


def delete_budget_item(trip_id: str, item_id: str) -> dict[str, Any]:
    current = build_default_budget(trip_id)
    items = [item for item in current.get("custom_expenses") or [] if item.get("id") != item_id]
    current["custom_expenses"] = items
    current["grand_total"] = int(current.get("attraction_total", 0)) + int(current.get("hotel_total", 0))
    for current_item in items:
        current["grand_total"] += int(current_item.get("amount") or 0)
    return set_budget_state(trip_id, current)


def generate_diary(trip_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    place = payload.get("place") or "파리"
    notes = payload.get("notes") or "오늘의 여행 기록"
    prompt = f"여행 일기 감성적으로 써줘. {place} 메모: {notes}"
    response = run_agent(AgentRunRequest(message=prompt, context={"trip_id": trip_id}))
    diary_payload = response.data.get("trip_diary", {}) if response.status in {"DONE", "PARTIAL"} else {}
    generated_text = diary_payload.get("generated_entry") or f"{place}에서의 순간을 감성적으로 기록했습니다. {notes}"
    mood_keywords = list(payload.get("emotion_tags") or [])[:5]
    return {
        "title": f"{place} 여행 기록",
        "generated_diary_text": generated_text,
        "mood_keywords": mood_keywords,
    }


def save_diary(trip_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return create_diary_entry(trip_id, payload)


def get_places(search: str = "", category: str = "", sort: str = "") -> list[dict[str, Any]]:
    return search_places(
        search=search,
        category=category,
        sort=sort,
        limit=60,
    )


def get_place(place_id: str) -> dict[str, Any] | None:
    return resolve_place(place_id)


def build_weather(days: int) -> dict[str, Any]:
    resolved_days = max(1, min(days, 10))
    forecast_days: list[dict[str, Any]] = []
    conditions = [
        ("Sunny", "☀️", "햇볕이 좋아 산책 코스를 잡기 좋습니다."),
        ("Cloudy", "☁️", "박물관과 카페를 섞어두면 편안합니다."),
        ("Light Rain", "🌦️", "실내 동선 위주로 움직이면 좋습니다."),
    ]
    for index in range(resolved_days):
        condition, icon, tip = conditions[index % len(conditions)]
        forecast_days.append(
            {
                "date": f"2026-05-{index + 13:02d}",
                "condition": condition,
                "icon": icon,
                "temp_min_c": 12 + index,
                "temp_max_c": 20 + index,
                "precipitation_chance": 20 + (index % 3) * 15,
                "travel_tip": tip,
            }
        )
    return {
        "city": "Paris",
        "country": "France",
        "timezone": "Europe/Paris",
        "days": forecast_days,
    }


def list_trip_diaries(trip_id: str) -> list[dict[str, Any]]:
    return list_diary_entries(trip_id)


def list_trip_reservations(trip_id: str) -> list[dict[str, Any]]:
    return list_reservations(trip_id)


def save_reservation(trip_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return create_reservation(trip_id, payload)
