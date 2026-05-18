from __future__ import annotations

import json
import os
import re
from typing import Any

from app.core.config import settings
from app.prompts.agent_profile_prompt import AGENT_PROFILE_PROMPT, CONTROLLER_FEW_SHOTS
from app.schemas.agent_action_schema import AgentActionPlan, AgentIntent


def plan_agent_action(
    user_request: str,
    *,
    context: dict[str, Any] | None = None,
) -> AgentActionPlan:
    """Classify a user request into a structured Agent action.

    The LLM path is intentionally opt-in so local regression tests remain
    deterministic. When enabled, its output is still validated by Pydantic and
    falls back to the deterministic classifier on any failure.
    """

    context = context or {}
    if _llm_controller_enabled():
        llm_action = _plan_with_llm(user_request, context=context)
        if llm_action is not None:
            return llm_action
    return _plan_with_rules(user_request, context=context)


def _llm_controller_enabled() -> bool:
    flag = os.getenv("ENABLE_LLM_CONTROLLER", "").strip().lower()
    return bool(settings.openai_api_key) and flag in {"1", "true", "yes", "on"}


def _plan_with_llm(user_request: str, *, context: dict[str, Any]) -> AgentActionPlan | None:
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key or "")
        prompt_payload = {
            "profile": AGENT_PROFILE_PROMPT,
            "few_shots": CONTROLLER_FEW_SHOTS,
            "user_request": user_request,
            "context": context,
            "allowed_intents": [intent.value for intent in AgentIntent],
        }
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_RESPONSE_MODEL", "gpt-4o-mini"),
            messages=[
                {
                    "role": "system",
                    "content": "Return only one JSON object matching the AgentActionPlan schema.",
                },
                {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False, default=str)},
            ],
            response_format={"type": "json_object"},
            max_tokens=900,
        )
        content = response.choices[0].message.content
        if not isinstance(content, str):
            return None
        data = json.loads(content)
        data.setdefault("raw_text", user_request)
        data.setdefault("source", "llm_controller")
        return AgentActionPlan.model_validate(data)
    except Exception:
        return None


def _plan_with_rules(user_request: str, *, context: dict[str, Any]) -> AgentActionPlan:
    text = str(user_request or "").strip()
    compact = re.sub(r"\s+", "", text.lower())
    has_trip_context = bool(context.get("trip_id") or context.get("current_trip") or context.get("itinerary_days"))

    if not text:
        return AgentActionPlan(
            intent=AgentIntent.GENERAL_TRAVEL_QA,
            action="clarify",
            confidence=0.0,
            needs_clarification=True,
            missing_required_fields=["message"],
            clarification_question="어떤 여행 계획을 도와드리면 될까요?",
            concise_decision_summary="Empty request needs clarification.",
            raw_text=text,
        )

    if _looks_like_hotel_search(compact):
        return AgentActionPlan(
            intent=AgentIntent.SEARCH_HOTEL,
            action="search_hotel",
            arguments={"query": text, "destination": "Paris"},
            confidence=0.78,
            needs_clarification=False,
            concise_decision_summary="Search hotel candidates using API-backed data.",
            raw_text=text,
        )

    if _looks_like_flight_search(compact):
        return AgentActionPlan(
            intent=AgentIntent.SEARCH_FLIGHT,
            action="search_flight",
            arguments={"query": text, "destination": "Paris"},
            confidence=0.78,
            needs_clarification=False,
            concise_decision_summary="Search flight candidates using API-backed data.",
            raw_text=text,
        )

    if has_trip_context and _looks_like_modify_request(compact):
        return AgentActionPlan(
            intent=AgentIntent.MODIFY_ITINERARY,
            action="modify_itinerary",
            arguments={"prompt": text, "target_day": context.get("target_day")},
            confidence=0.82,
            needs_clarification=False,
            concise_decision_summary="Patch the existing itinerary instead of regenerating it.",
            raw_text=text,
        )

    if _looks_like_place_search(compact):
        return AgentActionPlan(
            intent=AgentIntent.SEARCH_PLACE,
            action="search_place",
            arguments={"query": text, "destination": "Paris"},
            confidence=0.65,
            needs_clarification=False,
            concise_decision_summary="Search place candidates before planning.",
            raw_text=text,
        )

    return AgentActionPlan(
        intent=AgentIntent.CREATE_ITINERARY,
        action="create_itinerary",
        arguments={"prompt": text, "destination": "Paris"},
        confidence=0.74,
        needs_clarification=False,
        concise_decision_summary="Create a Paris itinerary from the natural-language request.",
        raw_text=text,
    )


def _looks_like_hotel_search(compact: str) -> bool:
    return any(token in compact for token in ("hotel", "호텔", "숙소", "숙박", "체크인", "checkin", "checkout"))


def _looks_like_flight_search(compact: str) -> bool:
    return any(token in compact for token in ("flight", "항공", "항공권", "비행기", "직항", "경유", "flyto"))


def _looks_like_place_search(compact: str) -> bool:
    return any(token in compact for token in ("장소찾", "어디있", "검색", "place", "근처맛집", "근처카페"))


def _looks_like_modify_request(compact: str) -> bool:
    return any(
        token in compact
        for token in (
            "수정",
            "바꿔",
            "빼줘",
            "빼고",
            "추가",
            "대신",
            "너무빡",
            "줄여",
            "둘째날",
            "첫째날",
            "셋째날",
            "day2",
            "modify",
            "change",
            "remove",
            "replace",
        )
    )

