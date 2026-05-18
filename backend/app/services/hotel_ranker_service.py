from __future__ import annotations

from math import atan2, cos, radians, sin, sqrt
from typing import Any


def rank_hotels_for_trip(
    hotels: list[dict[str, Any]],
    *,
    trip_state: dict[str, Any] | None = None,
    search_conditions: dict[str, Any] | None = None,
    memory_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Rank API-backed hotel candidates against the current itinerary context."""

    if not hotels:
        return []

    conditions = search_conditions or {}
    anchors = _itinerary_anchors(trip_state or {})
    center = _center_point(anchors)
    first_anchor = anchors[0] if anchors else None
    last_anchor = anchors[-1] if anchors else None
    budget = _number(conditions.get("budget") or conditions.get("max_price_per_night"))
    desired_amenities = [str(value).lower() for value in conditions.get("amenities") or [] if str(value).strip()]
    memory_tokens = _memory_tokens(memory_context or (trip_state or {}).get("memory_context") or {})

    ranked: list[dict[str, Any]] = []
    for hotel in hotels:
        item = dict(hotel)
        location = _candidate_location(item)
        distance_to_center = _distance_km(location, center) if location and center else None
        distance_to_first = _distance_km(location, first_anchor) if location and first_anchor else None
        distance_to_last = _distance_km(location, last_anchor) if location and last_anchor else None
        price = _number(item.get("price"))
        rating = _number(item.get("reviewScore") or item.get("rating"))
        amenity_score = _amenity_score(item, desired_amenities)
        memory_score = _memory_score(item, memory_tokens)

        score = 48.0
        if rating is not None:
            score += min(18.0, rating * 3.6)
        if distance_to_center is not None:
            score += _distance_score(distance_to_center)
        if distance_to_first is not None:
            score += _distance_score(distance_to_first, close_bonus=7.0, far_penalty=5.0)
        if distance_to_last is not None:
            score += _distance_score(distance_to_last, close_bonus=5.0, far_penalty=4.0)
        if budget and price:
            score += 12.0 if price <= budget else max(-16.0, -((price - budget) / max(budget, 1)) * 18.0)
        score += amenity_score + memory_score
        score = round(max(0.0, min(100.0, score)), 2)

        factors = {
            "budget_fit": _fit_label(price, budget),
            "location_fit": _distance_label(distance_to_center),
            "rating_score": rating,
            "amenity_match": amenity_score > 0,
            "distance_to_main_itinerary_area_km": distance_to_center,
            "distance_to_first_day_start_km": distance_to_first,
            "distance_to_last_day_end_km": distance_to_last,
            "route_convenience": _distance_label(distance_to_first if distance_to_first is not None else distance_to_center),
            "memory_preference_match": memory_score > 0,
            "overall_score": score,
        }
        item["score"] = score
        item["overall_score"] = score
        item["ranking_factors"] = factors
        item["ranking_reason"] = _hotel_reason(item, factors)
        item["legacy_reason"] = item.get("reason")
        item["reason"] = item["ranking_reason"]
        ranked.append(item)

    ranked.sort(key=lambda value: (-float(value.get("overall_score") or 0), int(value.get("rank") or 999)))
    for index, item in enumerate(ranked, start=1):
        item["rank"] = index
    return ranked


def _itinerary_anchors(trip_state: dict[str, Any]) -> list[dict[str, float]]:
    anchors: list[dict[str, float]] = []
    for day in trip_state.get("itinerary") or trip_state.get("itinerary_days") or []:
        for item in day.get("items") or []:
            if item.get("itemKind") == "gap":
                continue
            coords = ((item.get("place") or {}).get("coordinates") or {})
            lat = coords.get("lat")
            lng = coords.get("lng")
            if lat is not None and lng is not None:
                anchors.append({"lat": float(lat), "lng": float(lng)})
    return anchors


def _candidate_location(candidate: dict[str, Any]) -> dict[str, float] | None:
    lat = candidate.get("latitude") or candidate.get("lat")
    lng = candidate.get("longitude") or candidate.get("lng")
    if lat is None or lng is None:
        return None
    return {"lat": float(lat), "lng": float(lng)}


def _center_point(points: list[dict[str, float]]) -> dict[str, float] | None:
    if not points:
        return None
    return {
        "lat": sum(point["lat"] for point in points) / len(points),
        "lng": sum(point["lng"] for point in points) / len(points),
    }


def _distance_km(a: dict[str, float] | None, b: dict[str, float] | None) -> float | None:
    if not a or not b:
        return None
    radius = 6371.0
    lat1, lat2 = radians(a["lat"]), radians(b["lat"])
    dlat = radians(b["lat"] - a["lat"])
    dlng = radians(b["lng"] - a["lng"])
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return round(radius * 2 * atan2(sqrt(h), sqrt(1 - h)), 2)


def _distance_score(distance: float, *, close_bonus: float = 10.0, far_penalty: float = 8.0) -> float:
    if distance <= 1.5:
        return close_bonus
    if distance <= 3.5:
        return close_bonus * 0.55
    if distance <= 6:
        return 1.0
    return -far_penalty


def _distance_label(distance: float | None) -> str:
    if distance is None:
        return "unknown"
    if distance <= 1.5:
        return "excellent"
    if distance <= 3.5:
        return "good"
    if distance <= 6:
        return "fair"
    return "weak"


def _fit_label(price: float | None, budget: float | None) -> str:
    if price is None or budget is None:
        return "unknown"
    if price <= budget:
        return "within_budget"
    if price <= budget * 1.15:
        return "slightly_over"
    return "over_budget"


def _amenity_score(candidate: dict[str, Any], desired: list[str]) -> float:
    if not desired:
        return 0.0
    haystack = " ".join(str(value).lower() for value in [candidate, *(candidate.get("highlights") or [])])
    matches = sum(1 for amenity in desired if amenity in haystack)
    return min(8.0, matches * 3.0)


def _memory_tokens(memory_context: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("preference_summary", "long_term", "short_term", "topics"):
        value = memory_context.get(key)
        if isinstance(value, list):
            values.extend(str(item).lower() for item in value)
        elif value:
            values.append(str(value).lower())
    return values


def _memory_score(candidate: dict[str, Any], memory_tokens: list[str]) -> float:
    if not memory_tokens:
        return 0.0
    text = str(candidate).lower()
    return 5.0 if any(token and token in text for token in memory_tokens[:12]) else 0.0


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _hotel_reason(candidate: dict[str, Any], factors: dict[str, Any]) -> str:
    parts = []
    if factors["location_fit"] in {"excellent", "good"}:
        distance = factors.get("distance_to_main_itinerary_area_km")
        parts.append(f"it is close to the main itinerary area ({distance} km)")
    if factors["budget_fit"] == "within_budget":
        parts.append("it fits the stated budget")
    if candidate.get("reviewScore"):
        parts.append(f"review score is {candidate.get('reviewScore')}")
    if factors.get("memory_preference_match"):
        parts.append("it matches stored travel preferences")
    return "Recommended because " + ", ".join(parts[:3]) + "." if parts else "Recommended from API results with the best combined score."
