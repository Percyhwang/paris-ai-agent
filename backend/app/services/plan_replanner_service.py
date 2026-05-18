from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from typing import Any

from app.core import failure_types as ft
from app.core.repair_operations import (
    enforce_final_anchor,
    enforce_must_avoid,
    insert_place,
    move_place_to_final,
    move_place_to_time_slot,
    reduce_place_count_for_slow_pace,
    remove_duplicate_places,
    remove_place,
    reorder_by_anchor_order,
)
from app.services.llm_replanner_service import apply_llm_soft_replan

SLOT_START_TIMES = {
    "morning": "09:30",
    "lunch": "12:30",
    "afternoon": "15:00",
    "evening": "19:00",
    "night": "20:30",
}

MEAL_TARGETS = {
    "french_dinner": ("La Robe et le Palais", "evening"),
    "brunch": ("Twinkie Breakfast & Lunch", "morning"),
    "cafe": ("Fika", "afternoon"),
    "jazz_bar": ("Caveau de la Huchette", "evening"),
    "meal_preference": ("La Robe et le Palais", "evening"),
}

PLACE_QUERY_ALIASES: dict[str, tuple[str, ...]] = {
    "eiffel": ("Eiffel Tower",),
    "louvre": ("Louvre Museum",),
    "orsay": ("Musee d'Orsay",),
    "seine": ("Seine River Walk", "seine-river-walk"),
    "notre": ("Notre-Dame",),
    "sainte": ("Sainte-Chapelle",),
    "marais": ("marais",),
    "montmartre": ("Montmartre",),
    "arc": ("Arc de Triomphe",),
    "champs": ("Champs Elysees",),
    "luxembourg": ("Luxembourg Gardens",),
    "tuileries": ("Tuileries Garden",),
    "garnier": ("Palais Garnier",),
    "palais_royal": ("Palais Royal",),
    "jazz": ("Caveau de la Huchette",),
}

TARGET_ALIASES: dict[str, tuple[str, ...]] = {
    "eiffel": ("eiffel", "eiffeltower", "\uc5d0\ud3a0", "\uc5d0\ud3a0\ud0d1"),
    "louvre": ("louvre", "louvremuseum", "\ub8e8\ube0c\ub974"),
    "orsay": ("orsay", "museedorsay", "\uc624\ub974\uc138"),
    "seine": ("seine", "seineriver", "seineriverwalk", "\uc13c\uac15"),
    "notre": ("notre", "notredame", "\ub178\ud2b8\ub974\ub2f4"),
    "sainte": ("sainte", "saintechapelle", "\uc0dd\ud2b8\uc0e4\ud3a0"),
    "marais": ("marais", "lemarais", "\ub9c8\ub808"),
    "montmartre": ("montmartre", "sacrecoeur", "\ubabd\ub9c8\ub974\ud2b8"),
    "arc": ("arc", "arcdetriomphe", "\uac1c\uc120\ubb38"),
    "champs": ("champs", "champselysees", "\uc0f9\uc824\ub9ac\uc81c"),
    "luxembourg": ("luxembourg", "luxembourggardens", "\ub8e9\uc0c1\ubd80\ub974"),
    "tuileries": ("tuileries", "tuileriesgarden", "\ud280\ub974\ub9ac", "\ud290\ub974\ub9ac"),
    "garnier": ("garnier", "palaisgarnier", "opera", "\uac00\ub974\ub2c8\uc5d0", "\uc624\ud398\ub77c"),
    "palais_royal": ("palaisroyal", "\ud314\ub808\ub8e8\uc544\uc584"),
    "jazz": ("jazz", "jazzbar", "huchette", "\uc7ac\uc988", "\uc7ac\uc988\ubc14", "\ub974\uce74\ubcf4", "\uce74\ubcf4\ub4dc\ub77c\uc704\uc170\ud2b8", "\uc704\uc170\ud2b8"),
}

MEAL_CATEGORIES = {"restaurant", "bistro", "brasserie", "bar", "wine_bar", "cafe", "bakery"}


async def replan_payload(
    db: Any,
    payload: dict[str, Any],
    planning_brief: dict[str, Any],
    evaluation: dict[str, Any],
    *,
    prompt: str,
    language: str,
) -> dict[str, Any]:
    """Patch an itinerary using evaluator failures while preserving the draft structure."""

    del db  # reserved for the future LLM/search-backed replanner
    next_payload = deepcopy(payload)
    itinerary_days = list(next_payload.get("itinerary_days") or [])
    if not itinerary_days:
        return next_payload | {"_replanner_changed": False, "_replanner_actions": []}

    actions: list[dict[str, Any]] = []
    reflection_feedback = [
        str(value)
        for value in (evaluation.get("natural_language_feedback") or evaluation.get("feedback") or [])
        if str(value).strip()
    ]
    failures = [failure for failure in evaluation.get("failures") or [] if isinstance(failure, dict)]
    hard_failures = _structured_failures(evaluation, "hard")
    soft_failures = _structured_failures(evaluation, "soft")

    next_payload = apply_hard_repairs(next_payload, planning_brief, hard_failures, actions)
    next_payload = await apply_soft_repairs_with_llm_or_stub(next_payload, planning_brief, soft_failures, actions, language=language)
    itinerary_days = list(next_payload.get("itinerary_days") or [])

    _remove_include_constraint_avoid_conflicts(planning_brief, actions)
    suppressed_targets = [
        target
        for failure in failures
        if str(failure.get("type") or "") == "must_avoid_violation"
        and (target := str(failure.get("target") or "").strip())
        and not _is_explicit_include_constraint(planning_brief, target)
    ]
    if suppressed_targets:
        _suppress_targets_in_brief(planning_brief, suppressed_targets, actions)

    if _remove_avoided_items(itinerary_days, planning_brief, actions):
        pass
    if _dedupe_days(itinerary_days, actions):
        pass

    for failure in failures:
        issue_type = str(failure.get("type") or "")
        target = str(failure.get("target") or "").strip()
        if issue_type == "missing_required_anchor" and target:
            _ensure_target_present(itinerary_days, target, planning_brief, actions)
        elif issue_type == "must_avoid_violation" and target:
            _remove_target_items(itinerary_days, target, actions)
        elif issue_type == "time_slot_mismatch" and target:
            if target == "late_start":
                _apply_late_start(itinerary_days, actions)
            elif target == "early_finish":
                _apply_early_finish(itinerary_days, actions)
                _trim_for_early_finish(itinerary_days, planning_brief, actions)
            else:
                _move_target_to_slot(itinerary_days, target, _slot_for_target(target, planning_brief), actions)
        elif issue_type == "final_anchor_mismatch" and target:
            _ensure_target_present(itinerary_days, target, planning_brief, actions)
            _move_target_to_final(itinerary_days, target, actions)
        elif issue_type in {"duplicate_place", "duplicate_day_pattern"}:
            _dedupe_days(itinerary_days, actions)
        elif issue_type == "low_walking_violation":
            _reduce_low_walking_burden(itinerary_days, actions)
        elif issue_type == "pace_mismatch":
            _trim_for_pace(itinerary_days, planning_brief, actions)
        elif issue_type in {"helper_gap_quality", "story_flow"}:
            _trim_for_story_quality(itinerary_days, planning_brief, actions)
        elif issue_type == "museum_limit_violation":
            _trim_extra_museums(itinerary_days, planning_brief, actions)
        elif issue_type == "order_mismatch":
            _apply_ordered_anchors(itinerary_days, planning_brief, actions)

    _apply_place_constraints(itinerary_days, planning_brief, actions)
    _apply_locked_stops(itinerary_days, planning_brief, actions, suppressed_targets=suppressed_targets)
    _apply_ordered_anchors(itinerary_days, planning_brief, actions)
    _apply_final_anchor(itinerary_days, planning_brief, actions)
    for failure in failures:
        if str(failure.get("type") or "") == "final_anchor_mismatch" and str(failure.get("target") or "").strip():
            target = str(failure.get("target") or "").strip()
            _ensure_target_present(itinerary_days, target, planning_brief, actions)
            _move_target_to_final(itinerary_days, target, actions)
        if str(failure.get("target") or "") == "evening_only_start":
            _apply_evening_only_start(itinerary_days, actions)
    _trim_for_pace(itinerary_days, planning_brief, actions)
    if any(str(failure.get("type") or "") in {"helper_gap_quality", "story_flow"} for failure in failures):
        _trim_for_story_quality(itinerary_days, planning_brief, actions)
    _trim_overflow_items(itinerary_days, actions)
    _apply_final_anchor(itinerary_days, planning_brief, actions)
    _drop_items_after_final_anchor(itinerary_days, planning_brief, actions)
    _refresh_day_metadata(itinerary_days)

    next_payload["itinerary_days"] = itinerary_days
    selected_places = _selected_places(itinerary_days)
    if selected_places:
        next_payload["selected_places"] = selected_places
    trip = next_payload.setdefault("trip", {})
    trip["agent_replanner_actions"] = actions
    trip["agent_reflection_feedback"] = reflection_feedback
    trip["agent_replanner_context"] = {
        "language": language,
        "source_prompt": str(prompt or "")[:600],
        "feedback": reflection_feedback,
        "failure_count": len(failures),
    }
    return next_payload | {"_replanner_changed": bool(actions), "_replanner_actions": actions}


def apply_hard_repairs(
    plan: dict[str, Any],
    planning_brief: dict[str, Any],
    hard_failures: list[dict[str, Any]],
    actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Apply deterministic repairs for hard constraint failures."""

    next_plan = deepcopy(plan)
    actions = actions if actions is not None else []
    for failure in hard_failures:
        failure_type = str(failure.get("failure_type") or "")
        target = str(failure.get("target") or "").strip()
        if failure_type == ft.MUST_INCLUDE_MISSING and target:
            place = _resolve_target_place(target)
            if place is not None:
                next_plan = insert_place(next_plan, place)
                actions.append({"repair_operation": "insert_place", "failure_type": failure_type, "target": target})
        elif failure_type == ft.MUST_AVOID_INCLUDED and target:
            next_plan = remove_place(next_plan, target)
            actions.append({"repair_operation": "remove_place", "failure_type": failure_type, "target": target})
        elif failure_type == ft.FINAL_ANCHOR_VIOLATION and target:
            if _find_item(list(next_plan.get("itinerary_days") or []), target) is None:
                place = _resolve_target_place(target)
                if place is not None:
                    next_plan = insert_place(next_plan, place)
                    actions.append({"repair_operation": "insert_place", "failure_type": failure_type, "target": target})
            next_plan = move_place_to_final(next_plan, target)
            actions.append({"repair_operation": "move_place_to_final", "failure_type": failure_type, "target": target})
        elif failure_type == ft.ORDERED_ANCHOR_VIOLATION:
            anchors = [str(value) for value in planning_brief.get("ordered_anchors") or [] if str(value).strip()]
            next_plan = reorder_by_anchor_order(next_plan, anchors)
            actions.append({"repair_operation": "reorder_by_anchor_order", "failure_type": failure_type, "target": target})
        elif failure_type == ft.DUPLICATE_PLACE:
            next_plan = remove_duplicate_places(next_plan)
            actions.append({"repair_operation": "remove_duplicate_places", "failure_type": failure_type, "target": target})
        elif failure_type == ft.DUPLICATE_DAY_PATTERN:
            next_plan = remove_duplicate_places(next_plan)
            actions.append({"repair_operation": "remove_duplicate_day_pattern", "failure_type": failure_type, "target": target})
        elif failure_type == ft.LOW_WALKING_VIOLATION:
            _reduce_low_walking_burden(list(next_plan.get("itinerary_days") or []), actions)
            actions.append({"repair_operation": "reduce_walking_burden", "failure_type": failure_type, "target": target})

    next_plan = enforce_final_constraints(next_plan, planning_brief, actions)
    return next_plan


async def apply_soft_repairs_with_llm_or_stub(
    plan: dict[str, Any],
    planning_brief: dict[str, Any],
    soft_failures: list[dict[str, Any]],
    actions: list[dict[str, Any]] | None = None,
    *,
    language: str = "ko",
) -> dict[str, Any]:
    """Improve soft failures through the optional LLM replanner, then safe fallback operations."""

    next_plan = deepcopy(plan)
    actions = actions if actions is not None else []
    llm_result = apply_llm_soft_replan(
        next_plan,
        planning_brief,
        soft_failures,
        available_places=list(next_plan.get("candidate_places") or (next_plan.get("trip") or {}).get("candidate_places") or []),
        memory_context=dict(next_plan.get("memory_context") or (next_plan.get("trip") or {}).get("memory_context") or {}),
        route_summary=str((next_plan.get("trip") or {}).get("route_summary") or next_plan.get("route_summary") or ""),
        constraints=dict(next_plan.get("constraint_validation") or (next_plan.get("trip") or {}).get("constraint_validation") or {}),
        language=language,
    )
    if llm_result.get("applied"):
        actions.append({"repair_operation": "llm_soft_replanner", "failure_count": len(soft_failures)})
        return dict(llm_result.get("plan") or next_plan)
    if llm_result.get("warning"):
        actions.append({"repair_operation": "llm_soft_replanner_fallback", "warning": llm_result["warning"]})
    for failure in soft_failures:
        failure_type = str(failure.get("failure_type") or "")
        target = str(failure.get("target") or "").strip()
        if failure_type == ft.TIME_SLOT_MISMATCH and target:
            slot = _slot_for_target(target, planning_brief)
            next_plan = move_place_to_time_slot(next_plan, target, slot)
            actions.append({"repair_operation": "move_place_to_time_slot", "failure_type": failure_type, "target": target, "slot": slot})
        elif failure_type == ft.PACE_TOO_FAST:
            max_count = 4 if str(planning_brief.get("pace") or "").lower() == "slow" else 5
            next_plan = reduce_place_count_for_slow_pace(next_plan, max_count)
            actions.append({"repair_operation": "reduce_place_count_for_slow_pace", "failure_type": failure_type, "max_count": max_count})
        elif failure_type == ft.STORY_FLOW_WEAK and str(planning_brief.get("pace") or "").lower() == "slow":
            next_plan = reduce_place_count_for_slow_pace(next_plan, 4)
            actions.append({"repair_operation": "soft_stub_story_flow_trim", "failure_type": failure_type})
    return next_plan


def enforce_final_constraints(
    plan: dict[str, Any],
    planning_brief: dict[str, Any],
    actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    next_plan = deepcopy(plan)
    before = _selected_places(list(next_plan.get("itinerary_days") or []))
    next_plan = enforce_must_avoid(next_plan, [str(value) for value in planning_brief.get("must_avoid") or [] if str(value).strip()])
    next_plan = remove_duplicate_places(next_plan)
    next_plan = enforce_final_anchor(next_plan, str(planning_brief.get("final_anchor") or "").strip() or None)
    after = _selected_places(list(next_plan.get("itinerary_days") or []))
    if actions is not None and before != after:
        actions.append({"repair_operation": "enforce_final_constraints", "before_count": len(before), "after_count": len(after)})
    return next_plan


def _structured_failures(evaluation: dict[str, Any], severity: str) -> list[dict[str, Any]]:
    key = "hard_failures" if severity == "hard" else "soft_failures"
    failures = [failure for failure in evaluation.get(key) or [] if isinstance(failure, dict)]
    if failures:
        return failures
    return [
        failure
        for failure in evaluation.get("failures") or []
        if isinstance(failure, dict) and str(failure.get("severity") or "") == severity
    ]


def _ensure_target_present(
    itinerary_days: list[dict[str, Any]],
    target: str,
    planning_brief: dict[str, Any],
    actions: list[dict[str, Any]],
) -> bool:
    if _find_item(itinerary_days, target) is not None:
        return False
    place = _resolve_target_place(target)
    if place is None:
        return False
    slot = _slot_for_target(target, planning_brief)
    day = itinerary_days[0]
    items = list(day.get("items") or [])
    item = _item_from_place(place, day_number=int(day.get("day_number") or 1), index=len(items) + 1, slot=slot)
    insert_at = _insert_index_for_slot(items, slot)
    items.insert(insert_at, item)
    day["items"] = items
    actions.append({"type": "insert_anchor", "target": target, "slot": slot})
    return True


def _remove_avoided_items(
    itinerary_days: list[dict[str, Any]],
    planning_brief: dict[str, Any],
    actions: list[dict[str, Any]],
) -> bool:
    avoid_targets = [str(value) for value in planning_brief.get("must_avoid") or [] if str(value).strip()]
    if not avoid_targets:
        return False
    changed = False
    for day in itinerary_days:
        next_items = []
        for item in day.get("items") or []:
            if any(_matches_target(item, target) for target in avoid_targets):
                actions.append(
                    {
                        "type": "remove_avoided",
                        "target": str((item.get("place") or {}).get("name") or item.get("title") or ""),
                    }
                )
                changed = True
                continue
            next_items.append(item)
        day["items"] = next_items
    return changed


def _remove_target_items(
    itinerary_days: list[dict[str, Any]],
    target: str,
    actions: list[dict[str, Any]],
) -> bool:
    changed = False
    for day in itinerary_days:
        next_items = []
        for item in day.get("items") or []:
            if item.get("itemKind") != "gap" and _matches_target(item, target):
                actions.append(
                    {
                        "type": "remove_target",
                        "target": str((item.get("place") or {}).get("name") or item.get("title") or target),
                    }
                )
                changed = True
                continue
            next_items.append(item)
        day["items"] = next_items
    return changed


def _suppress_targets_in_brief(
    planning_brief: dict[str, Any],
    targets: list[str],
    actions: list[dict[str, Any]],
) -> None:
    if not targets:
        return
    original_include = list(planning_brief.get("must_include") or [])
    next_include = [
        value
        for value in original_include
        if not any(_target_matches_value(str(value), target) for target in targets)
    ]
    if len(next_include) != len(original_include):
        planning_brief["must_include"] = next_include
        actions.append({"type": "suppress_brief_include", "target": ", ".join(targets)})

    original_locks = list(planning_brief.get("locked_stops") or [])
    next_locks = [
        lock
        for lock in original_locks
        if not any(
            _target_matches_value(
                " ".join(str(lock.get(key) or "") for key in ("slug", "place_id", "label")),
                target,
            )
            for target in targets
        )
    ]
    if len(next_locks) != len(original_locks):
        planning_brief["locked_stops"] = next_locks
        actions.append({"type": "suppress_brief_lock", "target": ", ".join(targets)})

    existing_avoid = [str(value) for value in planning_brief.get("must_avoid") or [] if str(value).strip()]
    planning_brief["must_avoid"] = list(dict.fromkeys([*existing_avoid, *targets]))


def _remove_include_constraint_avoid_conflicts(planning_brief: dict[str, Any], actions: list[dict[str, Any]]) -> None:
    original_avoid = [str(value) for value in planning_brief.get("must_avoid") or [] if str(value).strip()]
    if not original_avoid:
        return
    next_avoid = [target for target in original_avoid if not _is_explicit_include_constraint(planning_brief, target)]
    if len(next_avoid) != len(original_avoid):
        planning_brief["must_avoid"] = next_avoid
        removed = [target for target in original_avoid if target not in next_avoid]
        actions.append({"type": "resolve_include_avoid_conflict", "target": ", ".join(removed)})


def _is_explicit_include_constraint(planning_brief: dict[str, Any], target: str) -> bool:
    canonical = _canonical_target(target)
    for constraint in planning_brief.get("place_constraints") or []:
        if not isinstance(constraint, dict):
            continue
        if str(constraint.get("intent") or "") == "avoid":
            continue
        constraint_target = str(constraint.get("target") or "")
        constraint_canonical = str(constraint.get("canonical") or "")
        if _target_matches_value(constraint_target, target) or (canonical and canonical == constraint_canonical):
            return True
    return False


def _dedupe_days(itinerary_days: list[dict[str, Any]], actions: list[dict[str, Any]]) -> bool:
    changed = False
    seen: set[str] = set()
    for day in itinerary_days:
        next_items = []
        for item in day.get("items") or []:
            if item.get("itemKind") == "gap":
                next_items.append(item)
                continue
            key = _item_key(item)
            if key and key in seen:
                actions.append({"type": "remove_duplicate", "target": key})
                changed = True
                continue
            if key:
                seen.add(key)
            next_items.append(item)
        day["items"] = next_items
    return changed


def _reduce_low_walking_burden(itinerary_days: list[dict[str, Any]], actions: list[dict[str, Any]]) -> bool:
    changed = False
    for day in itinerary_days:
        items = list(day.get("items") or [])
        next_items: list[dict[str, Any]] = []
        walk_like_count = 0
        for item in items:
            if item.get("itemKind") == "gap":
                next_items.append(item)
                continue
            if not _is_walk_like_item(item):
                next_items.append(item)
                continue
            walk_like_count += 1
            if walk_like_count > 1 and not item.get("finalAnchor"):
                actions.append({"type": "remove_low_walking_overload", "target": _item_key(item)})
                changed = True
                continue
            next_item = dict(item)
            duration = _item_duration_minutes(next_item)
            if duration > 55:
                start = _item_minutes(next_item)
                next_item["duration_minutes"] = 55
                next_item["estimated_duration"] = "55분"
                if start:
                    next_item["end_time"] = _format_minutes(start + 55)
                actions.append({"type": "cap_walk_duration", "target": _item_key(next_item), "duration_minutes": 55})
                changed = True
            next_items.append(next_item)
        day["items"] = next_items
    return changed


def _move_target_to_slot(
    itinerary_days: list[dict[str, Any]],
    target: str,
    slot: str,
    actions: list[dict[str, Any]],
) -> bool:
    found = _find_item_with_day(itinerary_days, target)
    if found is None:
        return False
    day, index, item = found
    next_item = dict(item)
    normalized_slot = "evening" if slot == "night" else slot
    next_item["time_slot"] = normalized_slot
    next_item["start_time"] = SLOT_START_TIMES.get(slot, SLOT_START_TIMES.get(normalized_slot, "15:00"))
    next_item["slotLockReason"] = "agent_replanner_time_slot"
    if slot in {"evening", "night"}:
        next_item["isNightViewSpot"] = bool(next_item.get("isNightViewSpot")) or _is_view_anchor(next_item)
    items = list(day.get("items") or [])
    items.pop(index)
    items.insert(_insert_index_for_slot(items, normalized_slot), next_item)
    day["items"] = items
    actions.append({"type": "move_to_slot", "target": target, "slot": slot})
    return True


def _move_target_to_final(itinerary_days: list[dict[str, Any]], target: str, actions: list[dict[str, Any]]) -> bool:
    found = _find_item_with_day(itinerary_days, target)
    if found is None:
        return False
    day, index, item = found
    items = list(day.get("items") or [])
    final_item = dict(item)
    final_item["time_slot"] = "evening"
    final_item["start_time"] = "20:15"
    final_item["finalAnchor"] = True
    final_item["finalAnchorKind"] = _canonical_target(target) or target
    final_item["slotLockReason"] = "agent_replanner_final_anchor"
    if _is_view_anchor(final_item):
        final_item["isNightViewSpot"] = True
    items.pop(index)
    items.append(final_item)
    day["items"] = items
    actions.append({"type": "move_to_final", "target": target})
    return True


def _apply_locked_stops(
    itinerary_days: list[dict[str, Any]],
    planning_brief: dict[str, Any],
    actions: list[dict[str, Any]],
    *,
    suppressed_targets: list[str] | None = None,
) -> None:
    suppressed_targets = suppressed_targets or []
    for lock in planning_brief.get("locked_stops") or []:
        if not isinstance(lock, dict):
            continue
        target = str(lock.get("slug") or lock.get("place_id") or lock.get("label") or "").strip()
        slot = str(lock.get("target_slot") or "").strip()
        if any(_target_matches_value(target, suppressed) for suppressed in suppressed_targets):
            continue
        if target and slot:
            _ensure_target_present(itinerary_days, target, planning_brief, actions)
            _move_target_to_slot(itinerary_days, target, slot, actions)


def _apply_place_constraints(
    itinerary_days: list[dict[str, Any]],
    planning_brief: dict[str, Any],
    actions: list[dict[str, Any]],
) -> bool:
    changed = False
    for constraint in planning_brief.get("place_constraints") or []:
        if not isinstance(constraint, dict):
            continue
        target = str(constraint.get("target") or constraint.get("canonical") or "").strip()
        intent = str(constraint.get("intent") or "").strip()
        slot = str(constraint.get("time_slot") or "").strip()
        if not target:
            continue
        if intent == "avoid":
            changed = _remove_target_items(itinerary_days, target, actions) or changed
            continue
        changed = _ensure_target_present(itinerary_days, target, planning_brief, actions) or changed
        if slot:
            changed = _move_target_to_slot(itinerary_days, target, slot, actions) or changed
        if constraint.get("final"):
            changed = _move_target_to_final(itinerary_days, target, actions) or changed
    return changed


def _apply_final_anchor(
    itinerary_days: list[dict[str, Any]],
    planning_brief: dict[str, Any],
    actions: list[dict[str, Any]],
) -> bool:
    target = str(planning_brief.get("final_anchor") or "").strip()
    if not target:
        return False
    changed = _ensure_target_present(itinerary_days, target, planning_brief, actions)
    return _move_target_to_final(itinerary_days, target, actions) or changed


def _drop_items_after_final_anchor(
    itinerary_days: list[dict[str, Any]],
    planning_brief: dict[str, Any],
    actions: list[dict[str, Any]],
) -> bool:
    target = str(planning_brief.get("final_anchor") or "").strip()
    if not target:
        return False
    changed = False
    for day in itinerary_days:
        items = list(day.get("items") or [])
        final_index = next(
            (
                index
                for index, item in enumerate(items)
                if item.get("itemKind") != "gap" and (item.get("finalAnchor") or _matches_target(item, target))
            ),
            None,
        )
        if final_index is None or final_index == len(items) - 1:
            continue
        removed = items[final_index + 1 :]
        hard_targets = [str(value) for value in planning_brief.get("must_include") or [] if str(value).strip()]
        hard_tail = [
            item
            for item in removed
            if item.get("itemKind") != "gap" and any(_matches_target(item, target) for target in hard_targets)
        ]
        day["items"] = [*items[:final_index], *hard_tail, items[final_index]]
        actions.append(
            {
                "type": "drop_after_final_anchor",
                "target": target,
                "removed": ", ".join(_item_label(item) for item in removed if item.get("itemKind") != "gap"),
            }
        )
        changed = True
    return changed


def _apply_ordered_anchors(
    itinerary_days: list[dict[str, Any]],
    planning_brief: dict[str, Any],
    actions: list[dict[str, Any]],
) -> bool:
    anchors = [str(value) for value in planning_brief.get("ordered_anchors") or [] if str(value).strip()]
    if len(anchors) < 2:
        return False
    changed = False
    for target in anchors:
        changed = _ensure_target_present(itinerary_days, target, planning_brief, actions) or changed
    for day in itinerary_days:
        items = list(day.get("items") or [])
        previous_index = -1
        previous_minutes = 8 * 60
        for target in anchors:
            found_index = next(
                (
                    index
                    for index, item in enumerate(items)
                    if item.get("itemKind") != "gap" and _matches_target(item, target)
                ),
                None,
            )
            if found_index is None:
                continue
            item = items.pop(found_index)
            insert_at = min(previous_index + 1, len(items))
            if found_index <= previous_index:
                changed = True
                actions.append({"type": "reorder_anchor", "target": target})
            items.insert(insert_at, item)
            current_minutes = _item_minutes(item)
            if current_minutes <= previous_minutes:
                adjusted = min(previous_minutes + 90, 22 * 60)
                item["start_time"] = f"{adjusted // 60:02d}:{adjusted % 60:02d}"
                item["time_slot"] = _slot_from_minutes(adjusted)
                item["slotLockReason"] = "agent_replanner_ordered_anchor"
                changed = True
            previous_index = insert_at
            previous_minutes = _item_minutes(item)
        day["items"] = items
    return changed


def _trim_for_pace(
    itinerary_days: list[dict[str, Any]],
    planning_brief: dict[str, Any],
    actions: list[dict[str, Any]],
) -> bool:
    if str(planning_brief.get("pace") or "").lower() != "slow":
        return False
    hard_targets = [str(value) for value in planning_brief.get("must_include") or [] if str(value).strip()]
    changed = False
    for day in itinerary_days:
        items = list(day.get("items") or [])
        real_count = sum(1 for item in items if item.get("itemKind") != "gap")
        while real_count > 5:
            remove_index = _low_priority_remove_index(items, hard_targets)
            if remove_index is None:
                break
            removed = items.pop(remove_index)
            actions.append(
                {
                    "type": "trim_for_pace",
                    "target": str((removed.get("place") or {}).get("name") or removed.get("title") or ""),
                }
            )
            changed = True
            real_count = sum(1 for item in items if item.get("itemKind") != "gap")
        day["items"] = items
    return changed


def _apply_late_start(itinerary_days: list[dict[str, Any]], actions: list[dict[str, Any]]) -> bool:
    for day in itinerary_days:
        for item in day.get("items") or []:
            if item.get("itemKind") == "gap":
                continue
            item["start_time"] = "10:30"
            item["time_slot"] = "morning"
            item["slotLockReason"] = "agent_replanner_late_start"
            actions.append({"type": "shift_late_start", "target": str((item.get("place") or {}).get("name") or item.get("title") or "")})
            return True
    return False


def _apply_early_finish(itinerary_days: list[dict[str, Any]], actions: list[dict[str, Any]]) -> bool:
    for day in itinerary_days:
        items = [item for item in day.get("items") or [] if item.get("itemKind") != "gap"]
        if not items:
            continue
        for item in reversed(items[:-1]):
            category = str((item.get("place") or {}).get("category") or "").lower()
            if category in MEAL_CATEGORIES:
                item["start_time"] = "18:15"
                item["time_slot"] = "evening"
                item["slotLockReason"] = "agent_replanner_early_dinner"
                break
        last = items[-1]
        last["start_time"] = "20:00"
        last["time_slot"] = "evening"
        last["slotLockReason"] = "agent_replanner_early_finish"
        actions.append({"type": "pull_early_finish", "target": str((last.get("place") or {}).get("name") or last.get("title") or "")})
        return True
    return False


def _apply_evening_only_start(itinerary_days: list[dict[str, Any]], actions: list[dict[str, Any]]) -> bool:
    changed = False
    for day in itinerary_days:
        items = [item for item in day.get("items") or [] if item.get("itemKind") != "gap"]
        if not items:
            continue
        next_items = [
            item
            for item in items
            if str(item.get("time_slot") or "") in {"evening", "night"} or _item_minutes(item) >= 17 * 60 or item.get("finalAnchor")
        ]
        if not next_items:
            next_items = items[-3:]
        for index, item in enumerate(next_items):
            if _item_minutes(item) < 17 * 60:
                item["start_time"] = ["18:00", "19:15", "20:30"][min(index, 2)]
                item["time_slot"] = "evening"
                item["slotLockReason"] = "agent_replanner_evening_only"
        if len(next_items) != len(items):
            changed = True
            actions.append({"type": "trim_for_evening_only", "target": str(len(items) - len(next_items))})
        day["items"] = next_items
        break
    return changed


def _trim_for_early_finish(
    itinerary_days: list[dict[str, Any]],
    planning_brief: dict[str, Any],
    actions: list[dict[str, Any]],
) -> bool:
    hard_targets = [str(value) for value in planning_brief.get("must_include") or [] if str(value).strip()]
    changed = False
    for day in itinerary_days:
        items = list(day.get("items") or [])
        while sum(1 for item in items if item.get("itemKind") != "gap") > 2:
            remove_index = _early_finish_remove_index(items, hard_targets)
            if remove_index is None:
                break
            removed = items.pop(remove_index)
            actions.append(
                {
                    "type": "trim_for_early_finish",
                    "target": str((removed.get("place") or {}).get("name") or removed.get("title") or ""),
                }
            )
            changed = True
        day["items"] = items
    return changed


def _early_finish_remove_index(items: list[dict[str, Any]], hard_targets: list[str]) -> int | None:
    for index, item in enumerate(items):
        if item.get("itemKind") == "gap":
            continue
        if item.get("finalAnchor"):
            continue
        if any(_matches_target(item, target) for target in hard_targets):
            continue
        category = str((item.get("place") or {}).get("category") or "").lower()
        if category in MEAL_CATEGORIES:
            continue
        return index
    for index, item in enumerate(items):
        if item.get("itemKind") == "gap" or item.get("finalAnchor"):
            continue
        if any(_matches_target(item, target) for target in hard_targets):
            continue
        return index
    return None


def _trim_extra_museums(
    itinerary_days: list[dict[str, Any]],
    planning_brief: dict[str, Any],
    actions: list[dict[str, Any]],
) -> bool:
    hard_targets = [str(value) for value in planning_brief.get("must_include") or [] if str(value).strip()]
    changed = False
    for day in itinerary_days:
        items = list(day.get("items") or [])
        museum_indices = [
            index
            for index, item in enumerate(items)
            if item.get("itemKind") != "gap" and _is_museum_item(item)
        ]
        if len(museum_indices) <= 1:
            continue
        preferred_keep = next(
            (
                index
                for index in museum_indices
                if any(_matches_target(items[index], target) for target in hard_targets)
            ),
            museum_indices[0],
        )
        next_items = []
        for index, item in enumerate(items):
            if index in museum_indices and index != preferred_keep:
                actions.append(
                    {
                        "type": "trim_extra_museum",
                        "target": str((item.get("place") or {}).get("name") or item.get("title") or ""),
                    }
                )
                changed = True
                continue
            next_items.append(item)
        day["items"] = next_items
    return changed


def _trim_for_story_quality(
    itinerary_days: list[dict[str, Any]],
    planning_brief: dict[str, Any],
    actions: list[dict[str, Any]],
) -> bool:
    hard_targets = [str(value) for value in planning_brief.get("must_include") or [] if str(value).strip()]
    pace = str(planning_brief.get("pace") or "").lower()
    limit = 4 if pace == "slow" else 5
    changed = False
    for day in itinerary_days:
        items = list(day.get("items") or [])
        while sum(1 for item in items if item.get("itemKind") != "gap") > limit:
            remove_index = _low_priority_remove_index(items, hard_targets)
            if remove_index is None:
                break
            removed = items.pop(remove_index)
            actions.append({"type": "trim_for_story_quality", "target": _item_label(removed)})
            changed = True
        day["items"] = items
    return changed


def _low_priority_remove_index(items: list[dict[str, Any]], hard_targets: list[str]) -> int | None:
    for index in range(len(items) - 1, -1, -1):
        item = items[index]
        if item.get("itemKind") == "gap":
            continue
        if item.get("finalAnchor"):
            continue
        if any(_matches_target(item, target) for target in hard_targets):
            continue
        category = str((item.get("place") or {}).get("category") or "").lower()
        if category in MEAL_CATEGORIES:
            continue
        return index
    return None


def _slot_for_target(target: str, planning_brief: dict[str, Any]) -> str:
    normalized = _normalize(target)
    canonical = _canonical_target(target)
    for constraint in planning_brief.get("place_constraints") or []:
        if not isinstance(constraint, dict):
            continue
        if str(constraint.get("intent") or "") == "avoid":
            continue
        slot = str(constraint.get("time_slot") or "").strip()
        if not slot:
            continue
        constraint_target = _normalize(str(constraint.get("target") or ""))
        constraint_canonical = str(constraint.get("canonical") or "").strip()
        if (
            (normalized and constraint_target and (normalized in constraint_target or constraint_target in normalized))
            or (canonical and canonical == constraint_canonical)
        ):
            return slot
    for lock in planning_brief.get("locked_stops") or []:
        if not isinstance(lock, dict):
            continue
        lock_text = _normalize(" ".join(str(lock.get(key) or "") for key in ("slug", "place_id", "label")))
        if normalized and (normalized in lock_text or lock_text in normalized):
            return str(lock.get("target_slot") or "afternoon")
    if target in MEAL_TARGETS:
        return MEAL_TARGETS[target][1]
    if canonical in {"eiffel", "seine", "arc", "jazz"}:
        return "evening"
    if canonical in {"notre", "sainte", "louvre", "orsay"}:
        return "morning"
    return "afternoon"


def _resolve_target_place(target: str) -> dict[str, Any] | None:
    try:
        from parser_api.services.place_catalog import resolve_place
    except ModuleNotFoundError:
        return None

    queries: list[str] = []
    if target in MEAL_TARGETS:
        queries.append(MEAL_TARGETS[target][0])
    canonical = _canonical_target(target)
    if canonical and canonical in PLACE_QUERY_ALIASES:
        queries.extend(PLACE_QUERY_ALIASES[canonical])
    queries.append(target)
    for query in dict.fromkeys(queries):
        place = resolve_place(query)
        if isinstance(place, dict):
            return place
    return None


def _item_from_place(place: dict[str, Any], *, day_number: int, index: int, slot: str) -> dict[str, Any]:
    normalized_slot = "evening" if slot == "night" else slot
    return {
        "id": f"{day_number}-{place.get('slug') or 'agent-place'}-{index}",
        "time_slot": normalized_slot,
        "start_time": SLOT_START_TIMES.get(slot, SLOT_START_TIMES.get(normalized_slot, "15:00")),
        "title": place.get("name") or "Paris stop",
        "place": {
            "place_id": place.get("slug") or place.get("place_id"),
            "name": place.get("name") or "Paris stop",
            "coordinates": dict(place.get("coordinates") or {"lat": 48.8566, "lng": 2.3522}),
            "category": place.get("category") or "landmark",
            "cuisine": place.get("cuisine"),
            "admission_fee": place.get("admission_fee"),
            "admission_fee_amount": place.get("admission_fee_amount"),
            "rating": place.get("rating"),
            "review_count": place.get("review_count"),
        },
        "description": place.get("short_description") or "Agent replanner inserted this stop to satisfy the request.",
        "estimated_duration": place.get("estimated_visit_duration") or "1 hour",
        "slotLockReason": "agent_replanner_inserted_anchor",
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


def _slot_from_minutes(minutes: int) -> str:
    if minutes < 12 * 60:
        return "morning"
    if minutes < 15 * 60:
        return "lunch"
    if minutes < 18 * 60:
        return "afternoon"
    return "evening"


def _trim_overflow_items(itinerary_days: list[dict[str, Any]], actions: list[dict[str, Any]]) -> bool:
    changed = False
    for day in itinerary_days:
        items = list(day.get("items") or [])
        if not items:
            continue

        kept: list[dict[str, Any]] = []
        for item in items:
            if item.get("itemKind") == "gap":
                kept.append(item)
                continue
            minutes = _item_minutes(item)
            if minutes < 24 * 60:
                kept.append(item)
                continue
            if item.get("finalAnchor"):
                item["start_time"] = "22:00"
                item["time_slot"] = "evening"
                item["slotLockReason"] = "agent_replanner_overflow_final"
                kept.append(item)
                actions.append({"type": "normalize_overflow_final", "target": _item_label(item)})
                changed = True
                continue
            actions.append({"type": "trim_overflow_item", "target": _item_label(item), "start_time": item.get("start_time")})
            changed = True

        real_items = [item for item in kept if item.get("itemKind") != "gap"]
        if not real_items and items:
            fallback_items = [item for item in items if item.get("itemKind") != "gap"][:4]
            for index, item in enumerate(fallback_items):
                minutes = (10 * 60) + (index * 120)
                item["start_time"] = f"{minutes // 60:02d}:{minutes % 60:02d}"
                item["time_slot"] = _slot_from_minutes(minutes)
            kept = fallback_items
            actions.append({"type": "normalize_overflow_day", "count": len(fallback_items)})
            changed = True

        if len(kept) != len(items) or changed:
            day["items"] = kept
    return changed


def _refresh_day_metadata(itinerary_days: list[dict[str, Any]]) -> None:
    for day in itinerary_days:
        items = list(day.get("items") or [])
        items = _sort_items_for_story(items)
        for index, item in enumerate(items, start=1):
            if not item.get("id"):
                item["id"] = f"{day.get('day_number') or 1}-agent-{index}"
        day["items"] = items
        names = [
            str((item.get("place") or {}).get("name") or item.get("title") or "")
            for item in items
            if item.get("itemKind") != "gap"
        ]
        if names:
            day["route_summary"] = f"Agent replanner adjusted: {', '.join(names[:4])}."


def _sort_items_for_story(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    real_items = [item for item in items if item.get("itemKind") != "gap"]
    gap_items = [item for item in items if item.get("itemKind") == "gap"]
    final_items = [item for item in real_items if item.get("finalAnchor")]
    normal_items = [item for item in real_items if not item.get("finalAnchor")]
    normal_items.sort(key=lambda item: _item_minutes(item) or 9999)
    if final_items:
        previous_minutes = max((_item_minutes(item) or 0 for item in normal_items), default=19 * 60)
        for final_item in final_items:
            final_minutes = _item_minutes(final_item) or 0
            if final_minutes <= previous_minutes:
                adjusted = min(previous_minutes + 45, 22 * 60)
                final_item["start_time"] = f"{adjusted // 60:02d}:{adjusted % 60:02d}"
                final_item["time_slot"] = "evening"
            previous_minutes = _item_minutes(final_item) or previous_minutes
    return [*normal_items, *final_items, *gap_items]


def _selected_places(itinerary_days: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for day in itinerary_days:
        for item in day.get("items") or []:
            if item.get("itemKind") == "gap":
                continue
            name = str((item.get("place") or {}).get("name") or item.get("title") or "").strip()
            if name:
                names.append(name)
    return list(dict.fromkeys(names))


def _find_item(itinerary_days: list[dict[str, Any]], target: str) -> dict[str, Any] | None:
    found = _find_item_with_day(itinerary_days, target)
    return found[2] if found else None


def _find_item_with_day(
    itinerary_days: list[dict[str, Any]],
    target: str,
) -> tuple[dict[str, Any], int, dict[str, Any]] | None:
    for day in itinerary_days:
        for index, item in enumerate(day.get("items") or []):
            if item.get("itemKind") == "gap":
                continue
            if _matches_target(item, target):
                return day, index, item
    return None


def _matches_target(item: dict[str, Any], target: str) -> bool:
    text = _item_text(item)
    norms = _target_norms(target)
    return any(norm and (norm in text or text in norm) for norm in norms)


def _target_matches_value(value: str, target: str) -> bool:
    value_norm = _normalize(value)
    return any(norm and (norm in value_norm or value_norm in norm) for norm in _target_norms(target))


def _target_norms(target: str) -> set[str]:
    normalized = _normalize(target)
    norms = {normalized} if normalized else set()
    canonical = _canonical_target(target)
    if canonical:
        norms.update(_normalize(alias) for alias in TARGET_ALIASES.get(canonical, ()))
        norms.update(_normalize(query) for query in PLACE_QUERY_ALIASES.get(canonical, ()))
    return {norm for norm in norms if norm}


def _canonical_target(target: str) -> str | None:
    normalized = _normalize(target)
    if not normalized:
        return None
    if target in MEAL_TARGETS:
        return target
    for canonical, aliases in TARGET_ALIASES.items():
        alias_norms = {_normalize(alias) for alias in aliases}
        if normalized in alias_norms or any(alias and alias in normalized for alias in alias_norms):
            return canonical
    return None


def _is_view_anchor(item: dict[str, Any]) -> bool:
    canonical_values = {"eiffel", "seine", "arc", "montmartre"}
    return any(_matches_target(item, value) for value in canonical_values)


def _item_label(item: dict[str, Any]) -> str:
    place = item.get("place") or {}
    return str(place.get("name") or item.get("title") or item.get("id") or "").strip()


def _item_key(item: dict[str, Any]) -> str:
    place = item.get("place") or {}
    for value in (place.get("place_id"), place.get("slug"), place.get("google_place_id"), place.get("name"), item.get("title")):
        normalized = _normalize(value)
        if normalized:
            return normalized
    return ""


def _item_text(item: dict[str, Any]) -> str:
    place = item.get("place") or {}
    values = [
        item.get("title"),
        place.get("name"),
        place.get("slug"),
        place.get("place_id"),
        place.get("category"),
        " ".join(str(value) for value in place.get("tags") or []),
        " ".join(str(value) for value in place.get("cuisine") or []),
    ]
    return _normalize(" ".join(str(value or "") for value in values))


def _is_walk_like_item(item: dict[str, Any]) -> bool:
    text = _item_text(item)
    return any(
        token in text
        for token in (
            "walk",
            "walking",
            "stroll",
            "promenade",
            "neighborhood",
            "street",
            "seine",
            "river",
            "\uc0b0\ucc45",
            "\uac77\uae30",
            "\uac78\uc5b4",
            "\uc13c\uac15",
            "\uc138\ub098",
        )
    )


def _item_duration_minutes(item: dict[str, Any]) -> int:
    try:
        return int(item.get("duration_minutes") or 0)
    except (TypeError, ValueError):
        return 0


def _item_minutes(item: dict[str, Any]) -> int:
    raw = str(item.get("start_time") or "")
    if ":" not in raw:
        return 0
    try:
        hour, minute = raw.split(":", 1)
        return int(hour) * 60 + int(minute)
    except (TypeError, ValueError):
        return 0


def _format_minutes(minutes: int) -> str:
    minutes = max(0, minutes)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _is_museum_item(item: dict[str, Any]) -> bool:
    place = item.get("place") or {}
    category = str(place.get("category") or "").lower()
    text = _item_text(item)
    return category in {"museum", "gallery"} or any(token in text for token in ("louvre", "orsay", "\ub8e8\ube0c\ub974", "\uc624\ub974\uc138"))


def _normalize(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).lower()
    return re.sub(r"[^0-9a-zA-Z\uac00-\ud7a3]+", "", normalized)
