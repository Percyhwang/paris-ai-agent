from __future__ import annotations

import re
from typing import Any


async def retrieve_candidate_places(
    db: Any | None,
    *,
    planning_brief: dict[str, Any] | None,
    limit: int = 40,
    min_candidates: int = 8,
) -> dict[str, Any]:
    """Retrieve candidate places from the internal DB first.

    Google/place API fallback is kept as a future hook because itinerary
    generation already uses the seeded place catalog. This service makes the
    Candidate Places stage explicit in the Agent trace without hallucinating
    places.
    """

    brief = planning_brief or {}
    context = {
        "source_order": ["place_db", "place_api_fallback"],
        "source": "place_db",
        "min_candidates": min_candidates,
        "candidates": [],
        "fallback_used": False,
        "warnings": [],
    }
    if db is None:
        context["warnings"].append("place_db_unavailable")
        return context

    query = _build_place_query(brief)
    try:
        docs = await db.places.find(query).limit(limit).to_list(length=limit)
    except Exception as exc:  # pragma: no cover - defensive DB guard
        context["warnings"].append(f"place_db_query_failed: {exc}")
        return context

    candidates = [_normalize_place_candidate(doc, source="place_db") for doc in docs if isinstance(doc, dict)]
    candidates = _dedupe_candidates([candidate for candidate in candidates if candidate])
    if len(candidates) < min_candidates:
        context["warnings"].append("place_db_candidates_below_threshold")
    context["candidates"] = candidates[:limit]
    return context


def _build_place_query(brief: dict[str, Any]) -> dict[str, Any]:
    categories = set()
    for value in [*list(brief.get("travel_style") or []), *list(brief.get("meal_preference") or [])]:
        token = str(value).lower()
        if "museum" in token:
            categories.add("museum")
        elif "cafe" in token or "coffee" in token:
            categories.add("cafe")
        elif "park" in token or "garden" in token:
            categories.add("park")
        elif "shopping" in token:
            categories.add("shopping")
        elif "food" in token or "dinner" in token or "bistro" in token:
            categories.update({"restaurant", "bistro", "brasserie"})
    must_include = [str(value) for value in brief.get("must_include") or [] if str(value).strip()]
    if must_include:
        pattern = "|".join(re.escape(value) for value in must_include[:8])
        return {"$or": [{"name": {"$regex": pattern, "$options": "i"}}, {"aliases": {"$regex": pattern, "$options": "i"}}]}
    if categories:
        return {"category": {"$in": sorted(categories)}}
    return {}


def _normalize_place_candidate(doc: dict[str, Any], *, source: str) -> dict[str, Any]:
    name = str(doc.get("name") or "").strip()
    if not name:
        return {}
    coordinates = doc.get("coordinates")
    if not isinstance(coordinates, dict):
        location = doc.get("location") if isinstance(doc.get("location"), dict) else {}
        point = location.get("coordinates") if isinstance(location, dict) else None
        if isinstance(point, list) and len(point) >= 2:
            coordinates = {"lat": point[1], "lng": point[0]}
    return {
        "place_id": str(doc.get("_id") or doc.get("place_id") or doc.get("slug") or ""),
        "name": name,
        "normalized_name": _normalize(name),
        "city": "Paris",
        "country": "France",
        "category": doc.get("category"),
        "tags": list(doc.get("tags") or []),
        "latitude": (coordinates or {}).get("lat") if isinstance(coordinates, dict) else None,
        "longitude": (coordinates or {}).get("lng") if isinstance(coordinates, dict) else None,
        "opening_hours": doc.get("opening_hours"),
        "estimated_duration": doc.get("estimated_visit_duration") or doc.get("estimated_duration"),
        "rating": doc.get("rating"),
        "source": source,
        "source_ref": str(doc.get("_id") or doc.get("source_ref") or ""),
        "confidence": 0.82 if source == "place_db" else 0.65,
    }


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for candidate in candidates:
        key = str(candidate.get("normalized_name") or candidate.get("place_id") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def _normalize(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]+", "", value.lower())

