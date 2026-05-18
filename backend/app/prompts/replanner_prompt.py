from __future__ import annotations

import json
from typing import Any


def build_replanner_prompt(
    planning_brief: dict[str, Any],
    current_plan: dict[str, Any] | list[dict[str, Any]],
    soft_failures: list[dict[str, Any]],
    available_places: list[dict[str, Any]],
    memory_context: dict[str, Any] | None = None,
    route_summary: str | None = None,
    constraints: dict[str, Any] | None = None,
) -> str:
    """Build a strict JSON-only prompt for future LLM soft repairs."""

    payload = {
        "planning_brief": planning_brief or {},
        "current_plan": current_plan or {},
        "soft_failures": soft_failures or [],
        "available_places": available_places or [],
        "memory_context": memory_context or {},
        "route_summary": route_summary or "",
        "constraints": constraints or {},
    }
    return (
        "You are a travel itinerary revision Agent.\n"
        "Your goal is to improve only the soft failures in the current itinerary.\n"
        "Rules:\n"
        "1. Never include a must_avoid place.\n"
        "2. Keep must_include places whenever possible.\n"
        "3. The final_anchor must remain the final stop.\n"
        "4. Preserve ordered_anchors order.\n"
        "5. Do not invent or hallucinate places. Use only available_places.\n"
        "6. Return JSON only.\n"
        "7. Do not return markdown, explanation text, comments, or prose.\n"
        "8. Hard constraints were already repaired by code, but you must not violate them again.\n"
        "9. Focus on pace, travel_style, meal_preference, story_flow, and preferred_time_slots.\n"
        "10. Return only the revised itinerary JSON.\n\n"
        "Input:\n"
        f"{json.dumps(payload, ensure_ascii=False, default=str)}"
    )
