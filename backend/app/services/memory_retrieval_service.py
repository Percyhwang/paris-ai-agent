from __future__ import annotations

import re
import hashlib
from datetime import UTC, date, datetime
from typing import Any

from bson import ObjectId


async def retrieve_memory_context(
    db: Any | None,
    *,
    user_id: str | None = None,
    prompt: str = "",
    planning_brief: dict[str, Any] | None = None,
    user_intent_analysis: dict[str, Any] | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    """Fetch user preference memory for the planning harness.

    This Mongo-backed version ranks recent memory documents against the current
    request and Planning Brief. It gives the Agent loop a real retrieval step
    while keeping the vector DB hook explicit for a future RAG upgrade.
    """

    brief = planning_brief or {}
    intent = user_intent_analysis or {}
    query_terms = _build_query_terms(prompt=prompt, planning_brief=brief, user_intent_analysis=intent)
    context: dict[str, Any] = {
        "short_term": _short_term_context(brief, intent),
        "long_term": [],
        "preference_summary": [],
        "retrieval": {
            "enabled": bool(db is not None and user_id),
            "source": "mongodb",
            "strategy": "keyword_scored_memory",
            "vector_ready": False,
            "limit": limit,
            "query_terms": query_terms[:24],
            "scored": False,
        },
    }
    if db is None or not user_id:
        context["retrieval"]["reason"] = "missing_db_or_user_id"
        return context

    try:
        fetch_limit = max(limit * 4, 32)
        memory_docs = await db.user_travel_memory.find({"user_id": user_id}).sort("updated_at", -1).to_list(length=fetch_limit)
    except Exception as exc:  # pragma: no cover - defensive integration guard
        context["retrieval"]["error"] = str(exc)
        return context

    long_term = _rank_memory_docs(memory_docs, query_terms=query_terms, limit=limit)
    context["long_term"] = long_term
    context["retrieval"]["scored"] = any(float(doc.get("score") or 0) > 0 for doc in long_term)
    context["retrieval"]["candidate_count"] = len([doc for doc in memory_docs if isinstance(doc, dict)])
    context["preference_summary"] = _summaries_from_memory(long_term)
    return context


async def update_feedback_memory(
    db: Any | None,
    *,
    user_id: str | None,
    trip_id: str | None = None,
    prompt: str = "",
    planning_brief: dict[str, Any] | None = None,
    itinerary_days: list[dict[str, Any]] | None = None,
    agent_evaluation: dict[str, Any] | None = None,
    source: str = "trip_generation",
    feedback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist a compact travel-preference memory document.

    The document is text-first for today's Mongo keyword retrieval, and also
    carries `embedding_text` so it can move to Vector DB/RAG later.
    """

    if db is None or not user_id:
        return {"stored": False, "reason": "missing_db_or_user_id"}

    brief = planning_brief or {}
    days = itinerary_days or []
    evaluation = agent_evaluation or {}
    now = datetime.now(UTC)
    selected_places = _extract_selected_places(days)
    tags = _memory_tags_from_brief(brief, evaluation)
    likes = _memory_likes_from_brief(brief)
    dislikes = _unique_texts(brief.get("must_avoid") or [])
    topics = _unique_texts([*tags, *likes, *selected_places[:8]])
    summary = _build_memory_summary(
        planning_brief=brief,
        selected_places=selected_places,
        agent_evaluation=evaluation,
        source=source,
    )
    preference = _build_memory_preference(brief)
    embedding_text = _build_embedding_text(
        summary=summary,
        preference=preference,
        prompt=prompt,
        tags=tags,
        places=selected_places,
        likes=likes,
        dislikes=dislikes,
    )
    memory_key = _memory_key(
        user_id=user_id,
        trip_id=trip_id,
        prompt=prompt,
        source=source,
        planning_brief=brief,
    )

    doc = {
        "user_id": user_id,
        "trip_id": str(trip_id) if trip_id else None,
        "memory_key": memory_key,
        "memory_type": "travel_preference_feedback",
        "source": source,
        "summary": summary,
        "preference": preference,
        "prompt": str(prompt or "").strip(),
        "tags": tags,
        "topics": topics,
        "places": selected_places[:24],
        "likes": likes,
        "dislikes": dislikes,
        "constraints": _memory_constraints_from_brief(brief),
        "planning_brief_digest": _planning_brief_digest(brief),
        "evaluation": _evaluation_digest(evaluation),
        "feedback": feedback or {},
        "embedding_text": embedding_text,
        "embedding": None,
        "embedding_model": None,
        "vector_ready": False,
        "rag_ready": True,
        "retrieval_strategy": "keyword_scored_memory",
        "updated_at": now,
    }

    try:
        await db.user_travel_memory.update_one(
            {"user_id": user_id, "memory_key": memory_key},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
    except Exception as exc:  # pragma: no cover - memory should not break planning
        return {"stored": False, "reason": "mongo_write_failed", "error": str(exc)}

    return {
        "stored": True,
        "memory_key": memory_key,
        "source": source,
        "summary": summary,
        "vector_ready": False,
    }


def merge_memory_into_planning_brief(
    planning_brief: dict[str, Any],
    memory_context: dict[str, Any] | None,
) -> dict[str, Any]:
    next_brief = dict(planning_brief or {})
    context = memory_context or {}
    next_brief["memory_context"] = context
    summaries = [str(value) for value in context.get("preference_summary") or [] if str(value).strip()]
    if summaries:
        next_brief["memory_preferences"] = summaries
    return next_brief


def _short_term_context(
    planning_brief: dict[str, Any],
    user_intent_analysis: dict[str, Any],
) -> list[dict[str, Any]]:
    context: list[dict[str, Any]] = []
    if planning_brief.get("must_include"):
        context.append(
            {
                "type": "must_include",
                "value": list(planning_brief.get("must_include") or []),
                "source": "current_request",
            }
        )
    if planning_brief.get("must_avoid"):
        context.append(
            {
                "type": "must_avoid",
                "value": list(planning_brief.get("must_avoid") or []),
                "source": "current_request",
            }
        )
    for intent in user_intent_analysis.get("hidden_intents") or []:
        if isinstance(intent, dict) and intent.get("insight"):
            context.append(
                {
                    "type": "hidden_intent",
                    "value": intent.get("insight"),
                    "source": intent.get("source") or "parser_inference",
                }
            )
    return context[:12]


def _summaries_from_memory(memory_docs: list[dict[str, Any]]) -> list[str]:
    summaries: list[str] = []
    for doc in memory_docs:
        for key in ("summary", "preference", "insight", "text"):
            value = str(doc.get(key) or "").strip()
            if value:
                summaries.append(value)
                break
    return list(dict.fromkeys(summaries))[:8]


def _build_query_terms(
    *,
    prompt: str,
    planning_brief: dict[str, Any],
    user_intent_analysis: dict[str, Any],
) -> list[str]:
    values: list[Any] = [prompt]
    for key in (
        "destination",
        "pace",
        "quality_focus",
        "transport_preference",
        "hotel_area_preference",
        "must_include",
        "must_avoid",
        "preferred_time_slots",
        "meal_preference",
        "travel_style",
        "ordered_anchors",
        "final_anchor",
        "raw_constraints",
    ):
        values.append(planning_brief.get(key))
    for constraint in planning_brief.get("place_constraints") or []:
        if isinstance(constraint, dict):
            values.extend([constraint.get("target"), constraint.get("canonical"), constraint.get("intent"), constraint.get("time_slot")])
    for key in (
        "detected_styles",
        "detected_interests",
        "detected_time_preferences",
        "detected_avoidances",
        "detected_companions",
        "detected_mobility",
        "detected_pace",
        "raw_constraints",
    ):
        values.append(user_intent_analysis.get(key))
    for hidden in user_intent_analysis.get("hidden_intents") or []:
        if isinstance(hidden, dict):
            values.extend([hidden.get("id"), hidden.get("type"), hidden.get("insight")])
    return _unique_terms(_terms_from_value(values))


def _rank_memory_docs(memory_docs: list[Any], *, query_terms: list[str], limit: int) -> list[dict[str, Any]]:
    scored: list[tuple[float, int, dict[str, Any]]] = []
    recent: list[dict[str, Any]] = []
    for index, raw_doc in enumerate(memory_docs):
        if not isinstance(raw_doc, dict):
            continue
        clean = _clean_doc(raw_doc)
        if not isinstance(clean, dict):
            continue
        recent.append(clean)
        score, matched_terms = _score_memory_doc(clean, query_terms)
        if score <= 0:
            continue
        clean["score"] = round(score, 3)
        clean["matched_terms"] = matched_terms[:12]
        clean["reason"] = _memory_match_reason(matched_terms)
        scored.append((score, index, clean))

    if scored:
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [doc for _, _, doc in scored[:limit]]

    fallback = []
    for doc in recent[:limit]:
        doc["score"] = 0.0
        doc["matched_terms"] = []
        doc["reason"] = "recent_memory_fallback"
        fallback.append(doc)
    return fallback


def _score_memory_doc(doc: dict[str, Any], query_terms: list[str]) -> tuple[float, list[str]]:
    if not query_terms:
        return 0.0, []
    searchable = _normalize_search_text(_memory_search_text(doc))
    if not searchable:
        return 0.0, []
    matched: list[str] = []
    score = 0.0
    tag_terms = set(_terms_from_value(doc.get("tags") or doc.get("topics") or []))
    preference_terms = set(
        _terms_from_value(
            [
                doc.get("places") or [],
                doc.get("selected_places") or [],
                doc.get("likes") or [],
                doc.get("dislikes") or [],
                doc.get("avoidances") or [],
            ]
        )
    )
    for term in query_terms:
        if not term or term not in searchable:
            continue
        matched.append(term)
        score += 1.0
        if term in tag_terms:
            score += 0.75
        if term in preference_terms:
            score += 0.5
    return score, list(dict.fromkeys(matched))


def _memory_search_text(doc: dict[str, Any]) -> str:
    fields = [
        "embedding_text",
        "summary",
        "preference",
        "insight",
        "text",
        "note",
        "feedback",
        "tags",
        "topics",
        "places",
        "selected_places",
        "likes",
        "dislikes",
        "avoidances",
        "travel_style",
        "meal_preference",
        "pace",
        "constraints",
    ]
    return " ".join(_flatten_text(doc.get(field)) for field in fields)


def _memory_match_reason(matched_terms: list[str]) -> str:
    if not matched_terms:
        return "recent_memory_fallback"
    return "matched_request_terms:" + ",".join(matched_terms[:5])


def _terms_from_value(value: Any) -> list[str]:
    flattened = _flatten_text(value)
    normalized = _normalize_search_text(flattened)
    if not normalized:
        return []
    terms = [part for part in normalized.split() if len(part) >= 2]
    compact = re.sub(r"\s+", "", normalized)
    if len(compact) >= 2:
        terms.append(compact)
    return terms


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(_flatten_text(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten_text(item) for item in value)
    return str(value)


def _normalize_search_text(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\uac00-\ud7a3]+", " ", str(value or "").lower()).strip()


def _unique_terms(terms: list[str]) -> list[str]:
    stopwords = {"and", "the", "with", "for", "plan", "여행", "일정", "해줘", "짜줘", "부탁해"}
    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        normalized = term.strip()
        if not normalized or normalized in stopwords or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique[:64]


def _clean_doc(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_clean_doc(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _clean_doc(item) for key, item in value.items()}
    return value


def _memory_key(
    *,
    user_id: str,
    trip_id: str | None,
    prompt: str,
    source: str,
    planning_brief: dict[str, Any],
) -> str:
    stable_parts = [
        user_id,
        source,
        str(trip_id or ""),
        _normalize_search_text(prompt)[:180],
        _normalize_search_text(_flatten_text(_planning_brief_digest(planning_brief)))[:220],
    ]
    return hashlib.sha1("|".join(stable_parts).encode("utf-8")).hexdigest()


def _extract_selected_places(itinerary_days: list[dict[str, Any]]) -> list[str]:
    places: list[str] = []
    for day in itinerary_days:
        if not isinstance(day, dict):
            continue
        for item in day.get("items") or []:
            if not isinstance(item, dict):
                continue
            place = item.get("place") if isinstance(item.get("place"), dict) else {}
            name = place.get("name") or item.get("title") or item.get("name")
            if name:
                places.append(str(name))
    return _unique_texts(places)


def _memory_tags_from_brief(
    planning_brief: dict[str, Any],
    agent_evaluation: dict[str, Any],
) -> list[str]:
    values: list[Any] = [
        planning_brief.get("pace"),
        planning_brief.get("travel_style"),
        planning_brief.get("meal_preference"),
        planning_brief.get("preferred_time_slots"),
        planning_brief.get("quality_focus"),
        planning_brief.get("transport_preference"),
    ]
    if planning_brief.get("night_view_required"):
        values.append("night_view")
    if bool(agent_evaluation.get("passed")):
        values.append("agent_passed")
    return _unique_texts(values)


def _memory_likes_from_brief(planning_brief: dict[str, Any]) -> list[str]:
    values: list[Any] = [
        planning_brief.get("must_include"),
        planning_brief.get("travel_style"),
        planning_brief.get("meal_preference"),
        planning_brief.get("preferred_time_slots"),
    ]
    final_anchor = planning_brief.get("final_anchor")
    if final_anchor:
        values.append(final_anchor)
    return _unique_texts(values)


def _memory_constraints_from_brief(planning_brief: dict[str, Any]) -> dict[str, Any]:
    return _clean_doc(
        {
            "must_include": list(planning_brief.get("must_include") or []),
            "must_avoid": list(planning_brief.get("must_avoid") or []),
            "preferred_time_slots": list(planning_brief.get("preferred_time_slots") or []),
            "final_anchor": planning_brief.get("final_anchor"),
            "ordered_anchors": list(planning_brief.get("ordered_anchors") or []),
            "pace": planning_brief.get("pace"),
        }
    )


def _planning_brief_digest(planning_brief: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "destination",
        "trip_days",
        "pace",
        "travel_style",
        "meal_preference",
        "must_include",
        "must_avoid",
        "preferred_time_slots",
        "night_view_required",
        "transport_preference",
        "quality_focus",
        "final_anchor",
        "ordered_anchors",
    )
    return _clean_doc({key: planning_brief.get(key) for key in keys if planning_brief.get(key) not in (None, [], {})})


def _evaluation_digest(agent_evaluation: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(agent_evaluation, dict):
        return {}
    checks = agent_evaluation.get("checks") if isinstance(agent_evaluation.get("checks"), dict) else {}
    failures = agent_evaluation.get("failures") if isinstance(agent_evaluation.get("failures"), list) else []
    warnings = agent_evaluation.get("warnings") if isinstance(agent_evaluation.get("warnings"), list) else []
    summary = agent_evaluation.get("summary") if isinstance(agent_evaluation.get("summary"), list) else []
    return _clean_doc(
        {
            "passed": agent_evaluation.get("passed"),
            "score": agent_evaluation.get("score"),
            "iterations": agent_evaluation.get("iterations"),
            "improved": agent_evaluation.get("improved"),
            "checks": checks,
            "failure_count": len(failures),
            "warning_count": len(warnings),
            "summary": summary[:8],
        }
    )


def _build_memory_summary(
    *,
    planning_brief: dict[str, Any],
    selected_places: list[str],
    agent_evaluation: dict[str, Any],
    source: str,
) -> str:
    style = ", ".join(_unique_texts(planning_brief.get("travel_style") or [])[:4])
    includes = ", ".join(_unique_texts(planning_brief.get("must_include") or [])[:4])
    slots = ", ".join(_unique_texts(planning_brief.get("preferred_time_slots") or [])[:4])
    places = ", ".join(selected_places[:5])
    status = "passed" if bool(agent_evaluation.get("passed")) else "saved"
    parts = [f"{source} {status} memory"]
    if style:
        parts.append(f"style={style}")
    if includes:
        parts.append(f"requested={includes}")
    if slots:
        parts.append(f"time={slots}")
    if places:
        parts.append(f"places={places}")
    return "; ".join(parts)


def _build_memory_preference(planning_brief: dict[str, Any]) -> str:
    parts: list[str] = []
    pace = planning_brief.get("pace")
    if pace:
        parts.append(f"pace:{pace}")
    styles = ", ".join(_unique_texts(planning_brief.get("travel_style") or [])[:6])
    if styles:
        parts.append(f"style:{styles}")
    meals = ", ".join(_unique_texts(planning_brief.get("meal_preference") or [])[:6])
    if meals:
        parts.append(f"meal:{meals}")
    avoids = ", ".join(_unique_texts(planning_brief.get("must_avoid") or [])[:6])
    if avoids:
        parts.append(f"avoid:{avoids}")
    if planning_brief.get("night_view_required"):
        parts.append("night_view_required:true")
    return "; ".join(parts)


def _build_embedding_text(
    *,
    summary: str,
    preference: str,
    prompt: str,
    tags: list[str],
    places: list[str],
    likes: list[str],
    dislikes: list[str],
) -> str:
    values = [
        summary,
        preference,
        prompt,
        "tags: " + ", ".join(tags),
        "places: " + ", ".join(places[:24]),
        "likes: " + ", ".join(likes),
        "dislikes: " + ", ".join(dislikes),
    ]
    return " | ".join(value for value in values if str(value or "").strip())[:4000]


def _unique_texts(value: Any) -> list[str]:
    flattened: list[str] = []

    def collect(item: Any) -> None:
        if item is None:
            return
        if isinstance(item, dict):
            for subitem in item.values():
                collect(subitem)
            return
        if isinstance(item, (list, tuple, set)):
            for subitem in item:
                collect(subitem)
            return
        text = str(item).strip()
        if text:
            flattened.append(text)

    collect(value)
    seen: set[str] = set()
    unique: list[str] = []
    for text in flattened:
        key = _normalize_search_text(text) or text.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(text)
    return unique[:64]
