from __future__ import annotations

from datetime import datetime
from typing import Any


def rank_flights_for_trip(
    flights: list[dict[str, Any]],
    *,
    trip_state: dict[str, Any] | None = None,
    search_conditions: dict[str, Any] | None = None,
    memory_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Rank API-backed flight candidates against schedule impact and preferences."""

    if not flights:
        return []

    conditions = search_conditions or {}
    budget = _number(conditions.get("budget") or conditions.get("max_price"))
    max_layovers = conditions.get("max_layovers")
    memory_tokens = _memory_tokens(memory_context or (trip_state or {}).get("memory_context") or {})
    ranked: list[dict[str, Any]] = []

    for flight in flights:
        item = dict(flight)
        price = _number(item.get("price"))
        duration = _number(item.get("durationHours"))
        stops = int(item.get("stops") or 0)
        arrival = _parse_dt(item.get("arrival"))
        return_departure = _parse_dt(item.get("returnDeparture"))
        first_day_impact = _first_day_impact(arrival)
        last_day_impact = _last_day_impact(return_departure)

        score = 54.0
        if price is not None and budget:
            score += 16.0 if price <= budget else max(-18.0, -((price - budget) / max(budget, 1)) * 18.0)
        if duration is not None:
            score += max(-14.0, 14.0 - max(0.0, duration - 13.0) * 2.0)
        score += 10.0 if stops == 0 else 4.0 if stops == 1 else -8.0
        if max_layovers is not None and stops > int(max_layovers):
            score -= 14.0
        score += _impact_score(first_day_impact)
        score += _impact_score(last_day_impact)
        if _memory_score(item, memory_tokens):
            score += 4.0
        score = round(max(0.0, min(100.0, score)), 2)

        factors = {
            "price_fit": _fit_label(price, budget),
            "duration_score": duration,
            "layover_score": "direct" if stops == 0 else "acceptable" if stops == 1 else "heavy",
            "departure_time_fit": _time_label(_parse_dt(item.get("departure"))),
            "arrival_time_fit": _time_label(arrival),
            "baggage_fit": "unknown",
            "first_day_impact": first_day_impact,
            "last_day_impact": last_day_impact,
            "itinerary_connection_score": _impact_score(first_day_impact) + _impact_score(last_day_impact),
            "memory_preference_match": _memory_score(item, memory_tokens) > 0,
            "overall_score": score,
        }
        item["score"] = score
        item["overall_score"] = score
        item["ranking_factors"] = factors
        item["ranking_reason"] = _flight_reason(item, factors)
        item["legacy_reason"] = item.get("reason")
        item["reason"] = item["ranking_reason"]
        ranked.append(item)

    ranked.sort(key=lambda value: (-float(value.get("overall_score") or 0), int(value.get("rank") or 999)))
    for index, item in enumerate(ranked, start=1):
        item["rank"] = index
    return ranked


def _first_day_impact(arrival: datetime | None) -> str:
    if arrival is None:
        return "unknown"
    hour = arrival.hour + arrival.minute / 60
    if hour <= 11:
        return "full_first_day_available"
    if hour <= 15:
        return "half_first_day_available"
    if hour <= 19:
        return "first_day_light_schedule_only"
    return "first_day_mostly_lost"


def _last_day_impact(departure: datetime | None) -> str:
    if departure is None:
        return "unknown"
    hour = departure.hour + departure.minute / 60
    if hour < 10:
        return "last_day_mostly_lost"
    if hour < 15:
        return "last_day_light_schedule_only"
    return "last_day_available"


def _impact_score(label: str) -> float:
    return {
        "full_first_day_available": 8.0,
        "half_first_day_available": 4.0,
        "first_day_light_schedule_only": -2.0,
        "first_day_mostly_lost": -8.0,
        "last_day_available": 6.0,
        "last_day_light_schedule_only": -1.0,
        "last_day_mostly_lost": -7.0,
    }.get(label, 0.0)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    return None


def _time_label(value: datetime | None) -> str:
    if value is None:
        return "unknown"
    if 6 <= value.hour < 11:
        return "morning"
    if 11 <= value.hour < 16:
        return "daytime"
    if 16 <= value.hour < 22:
        return "evening"
    return "late_night"


def _fit_label(price: float | None, budget: float | None) -> str:
    if price is None or budget is None:
        return "unknown"
    if price <= budget:
        return "within_budget"
    if price <= budget * 1.15:
        return "slightly_over"
    return "over_budget"


def _memory_tokens(memory_context: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("preference_summary", "long_term", "short_term", "topics"):
        value = memory_context.get(key)
        if isinstance(value, list):
            values.extend(str(item).lower() for item in value)
        elif value:
            values.append(str(value).lower())
    return values


def _memory_score(candidate: dict[str, Any], tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    text = str(candidate).lower()
    return 1.0 if any(token and token in text for token in tokens[:12]) else 0.0


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _flight_reason(candidate: dict[str, Any], factors: dict[str, Any]) -> str:
    parts = []
    if factors["layover_score"] == "direct":
        parts.append("it is direct")
    if factors["price_fit"] == "within_budget":
        parts.append("it fits the stated budget")
    if factors["first_day_impact"] in {"full_first_day_available", "half_first_day_available"}:
        parts.append("arrival keeps the first day usable")
    if factors["last_day_impact"] == "last_day_available":
        parts.append("return timing preserves the last day")
    if candidate.get("durationHours"):
        parts.append(f"total duration is {candidate.get('durationHours')} hours")
    return "Recommended because " + ", ".join(parts[:3]) + "." if parts else "Recommended from API results with the best combined score."
