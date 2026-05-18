from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from typing import Any


SLOT_START_TIMES = {
    "morning": "09:30",
    "lunch": "12:30",
    "afternoon": "15:00",
    "evening": "19:00",
    "night": "20:30",
}


def remove_place(plan: dict[str, Any] | list[dict[str, Any]], place_name: str) -> dict[str, Any] | list[dict[str, Any]]:
    next_plan = deepcopy(plan)
    for day in _plan_days(next_plan):
        day["items"] = [
            item
            for item in day.get("items") or []
            if item.get("itemKind") == "gap" or not _matches_place(item, place_name)
        ]
    return next_plan


def insert_place(plan: dict[str, Any] | list[dict[str, Any]], place: dict[str, Any]) -> dict[str, Any] | list[dict[str, Any]]:
    next_plan = deepcopy(plan)
    days = _plan_days(next_plan)
    if not days or not place:
        return next_plan
    target_day = days[0]
    items = list(target_day.get("items") or [])
    place_name = str(place.get("name") or place.get("title") or "").strip()
    if place_name and any(_matches_place(item, place_name) for item in items):
        return next_plan
    slot = str(place.get("time_slot") or place.get("slot") or "afternoon")
    item = _item_from_place(place, target_day, len(items) + 1, slot)
    items.insert(_insert_index_for_slot(items, slot), item)
    target_day["items"] = items
    return next_plan


def move_place_to_final(plan: dict[str, Any] | list[dict[str, Any]], place_name: str) -> dict[str, Any] | list[dict[str, Any]]:
    next_plan = deepcopy(plan)
    found = _pop_first_matching_item(next_plan, place_name)
    if found is None:
        return next_plan
    day, item = found
    item["time_slot"] = "evening"
    item["start_time"] = "20:15"
    item["finalAnchor"] = True
    item["finalAnchorKind"] = place_name
    item["slotLockReason"] = "repair_operation_final_anchor"
    if _looks_like_night_view(item):
        item["isNightViewSpot"] = True
    items = list(day.get("items") or [])
    items.append(item)
    day["items"] = items
    return next_plan


def move_place_to_time_slot(
    plan: dict[str, Any] | list[dict[str, Any]],
    place_name: str,
    target_time_slot: str,
) -> dict[str, Any] | list[dict[str, Any]]:
    next_plan = deepcopy(plan)
    found = _pop_first_matching_item(next_plan, place_name)
    if found is None:
        return next_plan
    day, item = found
    normalized_slot = "evening" if target_time_slot == "night" else target_time_slot
    item["time_slot"] = normalized_slot
    item["start_time"] = SLOT_START_TIMES.get(target_time_slot, SLOT_START_TIMES.get(normalized_slot, "15:00"))
    item["slotLockReason"] = "repair_operation_time_slot"
    items = list(day.get("items") or [])
    items.insert(_insert_index_for_slot(items, normalized_slot), item)
    day["items"] = items
    return next_plan


def remove_duplicate_places(plan: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any] | list[dict[str, Any]]:
    next_plan = deepcopy(plan)
    seen: set[str] = set()
    for day in _plan_days(next_plan):
        next_items: list[dict[str, Any]] = []
        for item in day.get("items") or []:
            if item.get("itemKind") == "gap":
                next_items.append(item)
                continue
            key = _item_key(item)
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            next_items.append(item)
        day["items"] = next_items
    return next_plan


def reduce_place_count_for_slow_pace(
    plan: dict[str, Any] | list[dict[str, Any]],
    max_count: int,
) -> dict[str, Any] | list[dict[str, Any]]:
    next_plan = deepcopy(plan)
    for day in _plan_days(next_plan):
        items = list(day.get("items") or [])
        while _real_item_count(items) > max_count:
            remove_index = _low_priority_remove_index(items)
            if remove_index is None:
                break
            items.pop(remove_index)
        day["items"] = items
    return next_plan


def reorder_by_anchor_order(
    plan: dict[str, Any] | list[dict[str, Any]],
    ordered_anchors: list[str],
) -> dict[str, Any] | list[dict[str, Any]]:
    next_plan = deepcopy(plan)
    anchors = [anchor for anchor in ordered_anchors if str(anchor).strip()]
    if len(anchors) < 2:
        return next_plan
    for day in _plan_days(next_plan):
        items = list(day.get("items") or [])
        ordered_items: list[dict[str, Any]] = []
        for anchor in anchors:
            index = next((idx for idx, item in enumerate(items) if _matches_place(item, anchor)), None)
            if index is not None:
                ordered_items.append(items.pop(index))
        if ordered_items:
            day["items"] = [*ordered_items, *items]
    return next_plan


def enforce_must_avoid(
    plan: dict[str, Any] | list[dict[str, Any]],
    must_avoid: list[str],
) -> dict[str, Any] | list[dict[str, Any]]:
    next_plan = deepcopy(plan)
    for target in must_avoid:
        next_plan = remove_place(next_plan, str(target))
    return next_plan


def enforce_final_anchor(
    plan: dict[str, Any] | list[dict[str, Any]],
    final_anchor: str | None,
) -> dict[str, Any] | list[dict[str, Any]]:
    if not final_anchor:
        return deepcopy(plan)
    return move_place_to_final(plan, final_anchor)


def _plan_days(plan: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(plan, dict):
        return list(plan.get("itinerary_days") or [])
    return list(plan or [])


def _pop_first_matching_item(
    plan: dict[str, Any] | list[dict[str, Any]],
    place_name: str,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    for day in _plan_days(plan):
        items = list(day.get("items") or [])
        for index, item in enumerate(items):
            if item.get("itemKind") != "gap" and _matches_place(item, place_name):
                found = items.pop(index)
                day["items"] = items
                return day, found
    return None


def _item_from_place(place: dict[str, Any], day: dict[str, Any], index: int, slot: str) -> dict[str, Any]:
    normalized_slot = "evening" if slot == "night" else slot
    name = str(place.get("name") or place.get("title") or "Paris stop")
    return {
        "id": f"{day.get('day_number') or 1}-repair-{_normalize(name) or index}-{index}",
        "time_slot": normalized_slot,
        "start_time": SLOT_START_TIMES.get(slot, SLOT_START_TIMES.get(normalized_slot, "15:00")),
        "title": name,
        "place": {
            "place_id": place.get("slug") or place.get("place_id"),
            "name": name,
            "coordinates": dict(place.get("coordinates") or {"lat": 48.8566, "lng": 2.3522}),
            "category": place.get("category") or "landmark",
        },
        "description": place.get("short_description") or place.get("description") or "Inserted by repair operation.",
        "estimated_duration": place.get("estimated_visit_duration") or "1 hour",
        "slotLockReason": "repair_operation_inserted",
    }


def _insert_index_for_slot(items: list[dict[str, Any]], slot: str) -> int:
    target_order = _slot_order(slot)
    final_index = next((index for index, item in enumerate(items) if item.get("finalAnchor")), None)
    upper_bound = final_index if final_index is not None else len(items)
    for index, item in enumerate(items[:upper_bound]):
        if _slot_order(str(item.get("time_slot") or "")) > target_order:
            return index
    return upper_bound


def _slot_order(slot: str) -> int:
    return {"morning": 1, "lunch": 2, "afternoon": 3, "evening": 4, "night": 5}.get(slot, 3)


def _real_item_count(items: list[dict[str, Any]]) -> int:
    return sum(1 for item in items if item.get("itemKind") != "gap")


def _low_priority_remove_index(items: list[dict[str, Any]]) -> int | None:
    for index in range(len(items) - 1, -1, -1):
        item = items[index]
        if item.get("itemKind") == "gap" or item.get("finalAnchor"):
            continue
        category = str((item.get("place") or {}).get("category") or "").lower()
        if category in {"restaurant", "bistro", "brasserie", "bar", "wine_bar", "cafe", "bakery"}:
            continue
        return index
    return None


def _matches_place(item: dict[str, Any], place_name: str) -> bool:
    target = _normalize(place_name)
    text = _normalize(
        " ".join(
            str(value or "")
            for value in (
                item.get("title"),
                (item.get("place") or {}).get("name"),
                (item.get("place") or {}).get("place_id"),
                (item.get("place") or {}).get("slug"),
            )
        )
    )
    return bool(target and (target in text or text in target))


def _item_key(item: dict[str, Any]) -> str:
    place = item.get("place") or {}
    for value in (place.get("place_id"), place.get("slug"), place.get("name"), item.get("title")):
        normalized = _normalize(value)
        if normalized:
            return normalized
    return ""


def _looks_like_night_view(item: dict[str, Any]) -> bool:
    text = _normalize(
        " ".join(
            str(value or "")
            for value in (item.get("title"), (item.get("place") or {}).get("name"), (item.get("place") or {}).get("category"))
        )
    )
    return any(token in text for token in ("eiffel", "seine", "arc", "night", "view", "야경", "센강", "에펠"))


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    ascii_normalized = re.sub(r"[^a-zA-Z0-9]+", "", text).lower()
    if ascii_normalized:
        return ascii_normalized
    return re.sub(r"[^0-9a-zA-Z\uac00-\ud7a3]+", "", str(value or "").lower())

