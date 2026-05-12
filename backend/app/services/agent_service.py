from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from fastapi import HTTPException

from app.core.config import settings
from app.schemas.trips import TripGenerateRequest

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


async def generate_trip_payload(request: TripGenerateRequest, language: str = "ko") -> dict[str, Any]:
    if settings.external_agent_api_url:
        return await _generate_with_external_agent(request, language=language)

    local_agent_response = _run_local_agent(request, language=language)
    if local_agent_response is not None:
        return _generated_payload_from_agent_response(local_agent_response, request, language=language)

    return _mock_trip_payload(request, language=language)


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
    trip.setdefault("trip_title", _title_from_prompt(request.prompt, _resolve_total_days(request, {}), language))
    trip.setdefault("prompt", request.prompt)
    trip.setdefault("total_days", _resolve_total_days(request, {}))
    trip.setdefault("style_tags", list(request.style_tags) or _infer_tags(request.prompt))
    trip.setdefault("status", "generated")
    trip.setdefault("route_summary", _copy(language, "Agent-generated Paris itinerary draft.", "Agent가 생성한 파리 일정 초안입니다."))
    return {
        "trip": trip,
        "itinerary_days": list(payload.get("itinerary_days") or []),
        "budget": dict(payload.get("budget") or _budget_from_days(int(trip.get("total_days") or 1))),
    }


def _generated_payload_from_frontend_trip(
    trip: dict[str, Any],
    request: TripGenerateRequest,
    language: str,
) -> dict[str, Any]:
    total_days = int(trip.get("total_days") or _resolve_total_days(request, {}))
    return {
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


def _generated_payload_from_agent_response(
    response: dict[str, Any],
    request: TripGenerateRequest,
    language: str,
) -> dict[str, Any]:
    status = str(response.get("status") or "")
    data = dict(response.get("data") or {})
    if status == "ASK":
        plan = dict(data.get("plan") or {})
        payload = _generated_payload_from_plan(plan, request, language=language)
        payload["trip"]["status"] = "needs_review"
        payload["trip"]["route_summary"] = (
            f"{payload['trip']['route_summary']} "
            f"{_copy(language, 'Agent asked for more detail, so this draft uses sensible defaults.', 'Agent가 추가 정보를 요청해 기본값으로 초안을 만들었습니다.')}"
        )
        return payload
    if status not in {"DONE", "PARTIAL"}:
        raise HTTPException(status_code=502, detail="Agent failed to generate a trip")

    plan = dict(data.get("plan") or {})
    if not plan:
        bundle_plan = _extract_plan_from_bundle(data.get("bundle"))
        if bundle_plan:
            plan = bundle_plan
    return _generated_payload_from_plan(plan, request, language=language)


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


def _generated_payload_from_plan(
    plan: dict[str, Any],
    request: TripGenerateRequest,
    language: str,
) -> dict[str, Any]:
    total_days = _resolve_total_days(request, plan)
    start, end = _resolve_dates(request, plan, total_days)
    themes = _plan_themes(plan)
    must_include = _plan_must_include(plan)

    itinerary_days = [
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
    ]

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
            "route_summary": _route_summary_from_plan(plan, language),
        },
        "itinerary_days": itinerary_days,
        "budget": _budget_from_days(total_days, plan),
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


def _plan_must_include(plan: dict[str, Any]) -> list[str]:
    preferences = plan.get("preferences") if isinstance(plan.get("preferences"), dict) else {}
    must_include = preferences.get("must_include") if isinstance(preferences, dict) else []
    if isinstance(must_include, list):
        return [str(place) for place in must_include if place]
    return []


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


def _mock_trip_payload(request: TripGenerateRequest, language: str) -> dict[str, Any]:
    total_days = request.total_days or _infer_days(request.prompt) or 3
    start = request.start_date or (date.today() + timedelta(days=45))
    end = request.end_date or (start + timedelta(days=total_days - 1))
    tags = request.style_tags or _infer_tags(request.prompt)

    itinerary_days = [
        _build_agent_day(
            day_number=index + 1,
            day_date=start + timedelta(days=index),
            total_days=total_days,
            themes=tags,
            must_include=[],
            plan={},
            language=language,
        )
        for index in range(total_days)
    ]

    return {
        "trip": {
            "trip_title": _title_from_prompt(request.prompt, total_days, language),
            "prompt": request.prompt,
            "start_date": start,
            "end_date": end,
            "total_days": total_days,
            "style_tags": tags,
            "status": "generated",
            "route_summary": _copy(
                language,
                "Paris itinerary draft generated from the local fallback planner.",
                "로컬 fallback planner로 생성한 파리 일정 초안입니다.",
            ),
        },
        "itinerary_days": itinerary_days,
        "budget": _budget_from_days(total_days),
    }


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
