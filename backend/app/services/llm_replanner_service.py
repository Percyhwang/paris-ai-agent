from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any

from app.core.config import settings
from app.core.repair_operations import enforce_final_anchor, enforce_must_avoid, remove_duplicate_places
from app.prompts.replanner_prompt import build_replanner_prompt


def llm_soft_replanner_enabled() -> bool:
    flag = os.getenv("ENABLE_LLM_REPLANNER", "").strip().lower()
    return bool(settings.openai_api_key) and flag in {"1", "true", "yes", "on"}


def apply_llm_soft_replan(
    plan: dict[str, Any],
    planning_brief: dict[str, Any],
    soft_failures: list[dict[str, Any]],
    *,
    available_places: list[dict[str, Any]] | None = None,
    memory_context: dict[str, Any] | None = None,
    route_summary: str | None = None,
    constraints: dict[str, Any] | None = None,
    language: str = "ko",
) -> dict[str, Any]:
    """Use an opt-in LLM to improve soft failures, then re-apply hard guards."""

    if not soft_failures:
        return {"applied": False, "plan": plan, "warning": None}
    if not llm_soft_replanner_enabled():
        return {"applied": False, "plan": plan, "warning": "llm_soft_replanner_disabled"}

    try:
        revised = _call_llm_replanner(
            plan,
            planning_brief,
            soft_failures,
            available_places=available_places or [],
            memory_context=memory_context or {},
            route_summary=route_summary,
            constraints=constraints or {},
            language=language,
        )
    except Exception as exc:  # pragma: no cover - external API defensive path
        return {"applied": False, "plan": plan, "warning": f"llm_soft_replanner_failed: {exc}"}

    normalized = _normalize_replanner_result(revised, plan)
    if normalized is None:
        return {"applied": False, "plan": plan, "warning": "llm_soft_replanner_invalid_json_shape"}

    if not _uses_available_places(normalized, available_places or []):
        return {"applied": False, "plan": plan, "warning": "llm_soft_replanner_unknown_place"}

    guarded = deepcopy(normalized)
    guarded = enforce_must_avoid(guarded, [str(value) for value in planning_brief.get("must_avoid") or [] if str(value).strip()])
    guarded = remove_duplicate_places(guarded)
    guarded = enforce_final_anchor(guarded, str(planning_brief.get("final_anchor") or "").strip() or None)
    return {"applied": True, "plan": guarded, "warning": None}


def _call_llm_replanner(
    plan: dict[str, Any],
    planning_brief: dict[str, Any],
    soft_failures: list[dict[str, Any]],
    *,
    available_places: list[dict[str, Any]],
    memory_context: dict[str, Any],
    route_summary: str | None,
    constraints: dict[str, Any],
    language: str,
) -> Any:
    from openai import OpenAI

    prompt = build_replanner_prompt(
        planning_brief,
        plan,
        soft_failures,
        available_places,
        memory_context=memory_context,
        route_summary=route_summary,
        constraints=constraints,
    )
    client = OpenAI(api_key=settings.openai_api_key or "")
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_RESPONSE_MODEL", "gpt-4o-mini"),
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "Return JSON only. Revise the itinerary for soft preference failures. "
                    "Do not expose reasoning. Do not invent hotels, flights, prices, or places."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=1800,
    )
    content = response.choices[0].message.content
    if not isinstance(content, str):
        raise ValueError("empty LLM response")
    return json.loads(content)


def _normalize_replanner_result(value: Any, fallback_plan: dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(value, dict) and isinstance(value.get("itinerary_days"), list):
        return value
    if isinstance(value, dict) and isinstance(value.get("days"), list):
        result = deepcopy(fallback_plan)
        result["itinerary_days"] = value["days"]
        return result
    if isinstance(value, dict) and isinstance(value.get("itinerary"), list):
        result = deepcopy(fallback_plan)
        result["itinerary_days"] = value["itinerary"]
        return result
    if isinstance(value, list):
        result = deepcopy(fallback_plan)
        result["itinerary_days"] = value
        return result
    return None


def _uses_available_places(plan: dict[str, Any], available_places: list[dict[str, Any]]) -> bool:
    if not available_places:
        return True
    allowed = {
        _normalize(str(value.get("name") or value.get("normalized_name") or value.get("place_id") or ""))
        for value in available_places
        if isinstance(value, dict)
    }
    if not allowed:
        return True
    for day in plan.get("itinerary_days") or []:
        for item in day.get("items") or []:
            if item.get("itemKind") == "gap":
                continue
            place = item.get("place") or {}
            name = _normalize(str(place.get("name") or item.get("title") or place.get("place_id") or ""))
            if name and not any(name in allowed_name or allowed_name in name for allowed_name in allowed):
                return False
    return True


def _normalize(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())
