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
    "saint_germain": ("Saint-Germain-des-Pres", "Saint-Germain cafe walk"),
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
    "saint_germain": ("saintgermain", "saintgermaindespres", "생제르맹", "생제르맹데프레"),
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


def _normalized_style_tokens(planning_brief: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for key in ("travel_style", "meal_preference"):
        for value in planning_brief.get(key) or []:
            token = str(value).strip().lower()
            if not token:
                continue
            tokens.add("romantic" if token == "romance" else token)
    trip_style = str(((planning_brief.get("party") or {}).get("trip_style")) or planning_brief.get("trip_style") or "").strip().lower()
    if trip_style:
        tokens.add(trip_style)
    source_text = _normalize(str(planning_brief.get("source_text") or ""))
    if "커플" in str(planning_brief.get("source_text") or "") or "couple" in source_text:
        tokens.add("couple")
    return tokens


def _day_item_limit(planning_brief: dict[str, Any], day: dict[str, Any] | None = None) -> int:
    pace = str(planning_brief.get("pace") or "").lower()
    if pace != "slow":
        return 5

    tokens = _normalized_style_tokens(planning_brief)
    romantic_focus = bool(tokens.intersection({"romantic", "couple"}))
    landmark_focus = bool(tokens.intersection({"landmark", "classic"}))
    if not romantic_focus and not landmark_focus:
        return 5
    if day is None:
        return 6 if romantic_focus or landmark_focus else 5

    items = [item for item in day.get("items") or [] if item.get("itemKind") != "gap"]
    has_real_meal = any(
        str(item.get("role") or ((item.get("place") or {}).get("role") or "")).lower() in {"lunch", "dinner"}
        or str((item.get("place") or {}).get("category") or "").lower() in {"restaurant", "bistro", "brasserie"}
        for item in items
    )
    has_cafe_or_dessert = any(_is_cafe_like_item(item) for item in items)
    has_evening_close = any(
        bool(item.get("isNightViewSpot"))
        or str(item.get("role") or ((item.get("place") or {}).get("role") or "")).lower() in {"dinner", "night_activity", "walking_route"}
        for item in items
    )
    main_count = sum(1 for item in items if _is_main_activity_item(item))
    if romantic_focus and landmark_focus and has_real_meal and has_evening_close and main_count >= 2:
        return 6
    if romantic_focus and has_real_meal and (has_cafe_or_dessert or has_evening_close):
        return 6
    if landmark_focus and has_real_meal and has_evening_close and main_count >= 2:
        return 6
    return 5


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
    next_payload = await apply_soft_repairs_with_llm_or_stub(
        next_payload,
        planning_brief,
        soft_failures,
        actions,
        language=language,
        evaluation=evaluation,
    )
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
            if target == "early_start":
                _apply_early_start(itinerary_days, actions)
            elif target == "late_start":
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
        elif issue_type in {"museum_limit_violation", "museum_density_violation"}:
            _trim_extra_museums(itinerary_days, planning_brief, actions)
        elif issue_type == "family_unsuitable_stop":
            for day in itinerary_days:
                _remove_family_unsuitable_items(day, planning_brief, actions)
        elif issue_type == "touristiness_mismatch":
            for day in itinerary_days:
                _soften_touristy_day(day, planning_brief, actions)
        elif issue_type == "concept_mismatch":
            _rebalance_requested_concepts(itinerary_days, planning_brief, target, actions)
        elif issue_type == "order_mismatch":
            _apply_ordered_anchors(itinerary_days, planning_brief, actions)
        elif issue_type == "too_many_cafes":
            _reduce_excess_cafes(itinerary_days, actions)
        elif issue_type in {"consecutive_cafe_chain", "consecutive_restaurant_chain"}:
            for day in itinerary_days:
                _ensure_role_diversity(day, planning_brief, actions)
        elif issue_type == "meal_heavy_day":
            _reduce_meal_heavy_day(itinerary_days, planning_brief, actions)
        elif issue_type == "pace_density_mismatch":
            for day in itinerary_days:
                _rebalance_day_density(day, planning_brief, actions)
        elif issue_type == "lunch_timing_bad":
            _repair_meal_slot(itinerary_days, "lunch", actions)
        elif issue_type == "dinner_timing_bad":
            _repair_meal_slot(itinerary_days, "dinner", actions)
        elif issue_type in {"art_focus_missing", "main_activity_missing"}:
            _ensure_default_main_activity(itinerary_days, planning_brief, actions, prefer_art=issue_type == "art_focus_missing")
        elif issue_type == "fatigue_without_break":
            for day in itinerary_days:
                _ensure_recovery_stop(day, actions, planning_brief)
        elif issue_type == "night_overload":
            for day in itinerary_days:
                _soften_night_tail(day, actions, planning_brief)
        elif issue_type in {"repetitive_category", "low_category_diversity", "experience_monotony"}:
            _reduce_repetitive_category_run(itinerary_days, actions)
        elif issue_type == "theme_missing":
            _rewrite_day_theme(itinerary_days, actions)
        elif issue_type == "generic_description_repetition":
            _rewrite_item_descriptions(itinerary_days, actions)

    _apply_daily_quality_repairs(itinerary_days, planning_brief, evaluation, actions)
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

    llm_repair_operations = [value for value in next_payload.pop("_llm_repair_operations", []) if isinstance(value, dict)]
    llm_unresolved_failures = [value for value in next_payload.pop("_llm_unresolved_failures", []) if isinstance(value, dict)]

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
        "llm_repair_operations": llm_repair_operations,
        "llm_reported_unresolved_failures": llm_unresolved_failures,
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
    evaluation: dict[str, Any] | None = None,
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
        constraints=_llm_replanner_constraints(
            next_plan,
            evaluation,
        ),
        language=language,
    )
    if llm_result.get("applied"):
        repair_operations = [value for value in llm_result.get("repair_operations") or [] if isinstance(value, dict)]
        unresolved_failures = [value for value in llm_result.get("unresolved_failures") or [] if isinstance(value, dict)]
        actions.append(
            {
                "repair_operation": "llm_soft_replanner",
                "failure_count": len(soft_failures),
                "llm_operation_count": len(repair_operations),
                "unresolved_failure_count": len(unresolved_failures),
            }
        )
        for operation in repair_operations:
            action = {
                "repair_operation": str(operation.get("type") or operation.get("repair_operation") or "llm_operation"),
                "source": "llm",
            }
            action.update(operation)
            actions.append(action)
        llm_plan = dict(llm_result.get("plan") or next_plan)
        llm_plan["_llm_repair_operations"] = repair_operations
        llm_plan["_llm_unresolved_failures"] = unresolved_failures
        return llm_plan
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
            max_count = _day_item_limit(planning_brief)
            next_plan = reduce_place_count_for_slow_pace(next_plan, max_count)
            actions.append({"repair_operation": "reduce_place_count_for_slow_pace", "failure_type": failure_type, "max_count": max_count})
        elif failure_type == ft.STORY_FLOW_WEAK and str(planning_brief.get("pace") or "").lower() == "slow":
            max_count = max(5, _day_item_limit(planning_brief))
            next_plan = reduce_place_count_for_slow_pace(next_plan, max_count)
            actions.append({"repair_operation": "soft_stub_story_flow_trim", "failure_type": failure_type, "max_count": max_count})
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


def _llm_replanner_constraints(
    plan: dict[str, Any],
    evaluation: dict[str, Any] | None,
) -> dict[str, Any]:
    constraints = dict(plan.get("constraint_validation") or (plan.get("trip") or {}).get("constraint_validation") or {})
    planning_brief = dict(plan.get("planning_brief") or (plan.get("trip") or {}).get("planning_brief") or {})
    if not isinstance(evaluation, dict):
        if planning_brief.get("quality_reflection"):
            constraints["quality_reflection"] = dict(planning_brief.get("quality_reflection") or {})
        if planning_brief.get("replan_history"):
            constraints["replan_history"] = list(planning_brief.get("replan_history") or [])[-4:]
        return constraints
    constraints["agent_evaluation"] = {
        "checks": dict(evaluation.get("checks") or {}),
        "quality_score_100": evaluation.get("quality_score_100"),
        "failures": [
            {
                "type": failure.get("type"),
                "target": failure.get("target"),
                "message": failure.get("message"),
                "severity": failure.get("severity"),
            }
            for failure in evaluation.get("failures") or []
            if isinstance(failure, dict)
        ],
        "repair_suggestions": list(evaluation.get("repair_suggestions") or []),
        "daily_quality": [
            {
                "day_number": day.get("day_number"),
                "passed": day.get("passed"),
                "errors": list(day.get("errors") or []),
                "warnings": list(day.get("warnings") or []),
                "repair_suggestions": list(day.get("repair_suggestions") or []),
                "quality_checks": dict(day.get("quality_checks") or {}),
            }
            for day in evaluation.get("daily_quality") or []
            if isinstance(day, dict)
        ],
    }
    if planning_brief.get("quality_reflection"):
        constraints["quality_reflection"] = dict(planning_brief.get("quality_reflection") or {})
    if planning_brief.get("replan_history"):
        constraints["replan_history"] = list(planning_brief.get("replan_history") or [])[-4:]
    return constraints


def _apply_daily_quality_repairs(
    itinerary_days: list[dict[str, Any]],
    planning_brief: dict[str, Any],
    evaluation: dict[str, Any] | None,
    actions: list[dict[str, Any]],
) -> bool:
    if not isinstance(evaluation, dict):
        return False

    changed = False
    for day_report in evaluation.get("daily_quality") or []:
        if not isinstance(day_report, dict) or bool(day_report.get("passed")):
            continue
        day = _find_day_by_number(itinerary_days, int(day_report.get("day_number") or 0))
        if day is None:
            continue

        issue_codes = {
            str(issue.get("code") or "").strip()
            for issue in day_report.get("issue_details") or []
            if isinstance(issue, dict) and str(issue.get("code") or "").strip()
        }
        quality_checks = dict(day_report.get("quality_checks") or {})
        if "too_many_cafes" in issue_codes or not bool(quality_checks.get("max_cafes_ok", True)):
            changed = _reduce_excess_cafes([day], actions) or changed
        if {"consecutive_cafe_chain", "consecutive_restaurant_chain"}.intersection(issue_codes):
            changed = _ensure_role_diversity(day, planning_brief, actions) or changed
        if "meal_heavy_day" in issue_codes:
            changed = _reduce_meal_heavy_day([day], planning_brief, actions) or changed
        if "missing_lunch" in issue_codes:
            changed = _ensure_meal_stop(day, "lunch", actions, planning_brief) or changed
        elif "lunch_timing_bad" in issue_codes:
            changed = _repair_meal_slot([day], "lunch", actions) or changed
        if "missing_dinner" in issue_codes:
            changed = _ensure_meal_stop(day, "dinner", actions, planning_brief) or changed
        elif "dinner_timing_bad" in issue_codes:
            changed = _repair_meal_slot([day], "dinner", actions) or changed
        if "pace_density_mismatch" in issue_codes or not bool(quality_checks.get("pace_density_ok", True)):
            changed = _rebalance_day_density(day, planning_brief, actions) or changed
        if "museum_density_violation" in issue_codes or not bool(quality_checks.get("museum_density_ok", True)):
            changed = _trim_extra_museums([day], planning_brief, actions) or changed
        if "main_activity_missing" in issue_codes or not bool(quality_checks.get("main_activity_exists", True)):
            changed = _ensure_default_main_activity([day], planning_brief, actions, prefer_art=False) or changed
        if "art_focus_missing" in issue_codes or not bool(quality_checks.get("art_day_ok", True)):
            changed = _ensure_default_main_activity([day], planning_brief, actions, prefer_art=True) or changed
        if "family_unsuitable_stop" in issue_codes or not bool(quality_checks.get("family_friendly_ok", True)):
            changed = _remove_family_unsuitable_items(day, planning_brief, actions) or changed
        if "touristiness_mismatch" in issue_codes or not bool(quality_checks.get("local_style_ok", True)):
            changed = _soften_touristy_day(day, planning_brief, actions) or changed
        if "fatigue_without_break" in issue_codes or not bool(quality_checks.get("recovery_rhythm_ok", True)):
            changed = _ensure_recovery_stop(day, actions, planning_brief) or changed
        if "night_overload" in issue_codes or not bool(quality_checks.get("night_tail_ok", True)):
            changed = _soften_night_tail(day, actions, planning_brief) or changed
        if (
            {"low_category_diversity", "experience_monotony", "repetitive_category"}.intersection(issue_codes)
            or not bool(quality_checks.get("category_diversity_ok", True))
        ):
            changed = _ensure_role_diversity(day, planning_brief, actions) or changed
        if "theme_missing" in issue_codes or not bool(quality_checks.get("theme_exists", True)):
            changed = _rewrite_day_theme([day], actions) or changed
        if "generic_description_repetition" in issue_codes:
            changed = _rewrite_item_descriptions([day], actions) or changed

        if not issue_codes and not bool(day_report.get("passed")):
            changed = _trim_for_story_quality([day], planning_brief, actions) or changed
            changed = _rewrite_day_theme([day], actions) or changed
            changed = _rewrite_item_descriptions([day], actions) or changed
    return changed


def _find_day_by_number(itinerary_days: list[dict[str, Any]], day_number: int) -> dict[str, Any] | None:
    if day_number <= 0:
        return itinerary_days[0] if itinerary_days else None
    for day in itinerary_days:
        if int(day.get("day_number") or 0) == day_number:
            return day
    return None


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
    found = _find_item_with_day(itinerary_days, target, reverse=True)
    if found is None:
        return False
    day, index, item = found
    _clear_final_anchor_flags(itinerary_days)
    items = list(day.get("items") or [])
    items.pop(index)
    day["items"] = items
    final_day = itinerary_days[-1]
    final_day_items = list(final_day.get("items") or [])
    final_item = dict(item)
    final_item["time_slot"] = "evening"
    final_item["start_time"] = "20:15"
    final_item["finalAnchor"] = True
    final_item["finalAnchorKind"] = _canonical_target(target) or target
    final_item["slotLockReason"] = "agent_replanner_final_anchor"
    if _is_view_anchor(final_item):
        final_item["isNightViewSpot"] = True
    insert_at = next((i for i, existing in enumerate(final_day_items) if existing.get("itemKind") == "gap"), len(final_day_items))
    final_day_items.insert(insert_at, final_item)
    final_day["items"] = final_day_items
    actions.append({"type": "move_to_final", "target": target})
    return True


def _clear_final_anchor_flags(itinerary_days: list[dict[str, Any]]) -> None:
    for day in itinerary_days:
        for item in day.get("items") or []:
            item.pop("finalAnchor", None)
            item.pop("finalAnchorKind", None)
            if str(item.get("slotLockReason") or "") == "agent_replanner_final_anchor":
                item.pop("slotLockReason", None)


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
        limit = _day_item_limit(planning_brief, day)
        real_count = sum(1 for item in items if item.get("itemKind") != "gap")
        while real_count > limit:
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


def _apply_early_start(itinerary_days: list[dict[str, Any]], actions: list[dict[str, Any]]) -> bool:
    for day in itinerary_days:
        items = [item for item in day.get("items") or [] if item.get("itemKind") != "gap"]
        if not items:
            continue
        first_minutes = _item_minutes(items[0])
        if first_minutes is not None and first_minutes < 11 * 60 + 30 and str(items[0].get("time_slot") or "") == "morning":
            return False

        candidate_index = next(
            (
                index
                for index, item in enumerate(items)
                if not item.get("finalAnchor")
                and str(item.get("time_slot") or "").lower() not in {"evening", "night"}
                and str((item.get("place") or {}).get("category") or "").lower() not in {"bar", "wine_bar"}
            ),
            None,
        )
        if candidate_index is None:
            candidate_index = next((index for index, item in enumerate(items) if not item.get("finalAnchor")), None)
        if candidate_index is None:
            candidate_index = 0

        item = items.pop(candidate_index)
        items.insert(0, item)
        item["start_time"] = "09:15"
        item["time_slot"] = "morning"
        item["slotLockReason"] = "agent_replanner_early_start"
        day["items"] = items
        actions.append({"type": "pull_early_start", "target": str((item.get("place") or {}).get("name") or item.get("title") or "")})
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


def _reduce_excess_cafes(itinerary_days: list[dict[str, Any]], actions: list[dict[str, Any]]) -> bool:
    changed = False
    for day in itinerary_days:
        items = list(day.get("items") or [])
        cafe_indices = [
            index
            for index, item in enumerate(items)
            if item.get("itemKind") != "gap" and _is_cafe_like_item(item)
        ]
        while len(cafe_indices) > 2:
            remove_index = cafe_indices[-1]
            removed = items.pop(remove_index)
            actions.append({"type": "reduce_excess_cafe", "target": _item_label(removed)})
            cafe_indices = [
                index
                for index, item in enumerate(items)
                if item.get("itemKind") != "gap" and _is_cafe_like_item(item)
            ]
            changed = True
        day["items"] = items
    return changed


def _reduce_meal_heavy_day(
    itinerary_days: list[dict[str, Any]],
    planning_brief: dict[str, Any],
    actions: list[dict[str, Any]],
) -> bool:
    hard_targets = [str(value) for value in planning_brief.get("must_include") or [] if str(value).strip()]
    changed = False
    for day in itinerary_days:
        items = list(day.get("items") or [])
        while _meal_like_ratio(items) >= 0.6 and len([item for item in items if item.get("itemKind") != "gap"]) > 4:
            remove_index = _meal_heavy_remove_index(items, hard_targets)
            if remove_index is None:
                break
            removed = items.pop(remove_index)
            actions.append({"type": "reduce_meal_heaviness", "target": _item_label(removed)})
            changed = True
        day["items"] = items
    return changed


def _remove_family_unsuitable_items(
    day: dict[str, Any],
    planning_brief: dict[str, Any],
    actions: list[dict[str, Any]],
) -> bool:
    hard_targets = [str(value) for value in planning_brief.get("must_include") or [] if str(value).strip()]
    items = list(day.get("items") or [])
    next_items: list[dict[str, Any]] = []
    changed = False
    for item in items:
        if item.get("itemKind") == "gap":
            next_items.append(item)
            continue
        category = str((item.get("place") or {}).get("category") or "").lower()
        role = str(item.get("role") or ((item.get("place") or {}).get("role") or "")).lower()
        start_minutes = _item_minutes(item)
        protected = item.get("finalAnchor") or any(_matches_target(item, target) for target in hard_targets)
        unsuitable = (
            category in {"bar", "wine_bar"}
            or role == "night_activity"
            or (
                start_minutes >= 20 * 60 + 30
                and not bool(item.get("isNightViewSpot"))
                and role not in {"dinner", "walking_route"}
            )
        )
        if unsuitable and not protected:
            actions.append({"type": "remove_family_unsuitable", "target": _item_label(item)})
            changed = True
            continue
        if unsuitable and protected and start_minutes >= 20 * 60 + 30 and role not in {"dinner", "walking_route"}:
            item["time_slot"] = "evening"
            item["start_time"] = "19:15"
            item["slotLockReason"] = "agent_replanner_family_friendly"
            actions.append({"type": "retime_family_unsuitable", "target": _item_label(item), "slot": "evening"})
            changed = True
        next_items.append(item)
    day["items"] = next_items
    if _day_roles(day).isdisjoint({"walking_route"}):
        changed = _ensure_supporting_walk_stop(day, actions, planning_brief) or changed
    if "dinner" not in _day_roles(day):
        changed = _ensure_meal_stop(day, "dinner", actions, planning_brief) or changed
    changed = _soften_night_tail(day, actions, planning_brief) or changed
    return changed


def _soften_touristy_day(
    day: dict[str, Any],
    planning_brief: dict[str, Any],
    actions: list[dict[str, Any]],
) -> bool:
    hard_targets = [str(value) for value in planning_brief.get("must_include") or [] if str(value).strip()]
    items = list(day.get("items") or [])
    tourist_heavy_indices = [
        index
        for index, item in enumerate(items)
        if item.get("itemKind") != "gap" and _is_tourist_heavy_item(item)
    ]
    local_support_count = sum(
        1
        for item in items
        if item.get("itemKind") != "gap"
        and (
            str((item.get("place") or {}).get("category") or "").lower() in {"neighborhood", "park", "cafe", "bakery"}
            or str(item.get("role") or "").lower() == "walking_route"
        )
    )
    changed = False
    if len(tourist_heavy_indices) >= 3 and local_support_count <= 1:
        remove_index = next(
            (
                index
                for index in reversed(tourist_heavy_indices)
                if not items[index].get("finalAnchor")
                and not any(_matches_target(items[index], target) for target in hard_targets)
                and not _is_meal_like_item(items[index])
            ),
            None,
        )
        if remove_index is not None:
            removed = items.pop(remove_index)
            day["items"] = items
            actions.append({"type": "replace_touristy_stop", "target": _item_label(removed)})
            changed = True
    if _day_roles(day).isdisjoint({"walking_route"}):
        changed = _ensure_supporting_walk_stop(day, actions, planning_brief) or changed
    return changed


def _repair_meal_slot(itinerary_days: list[dict[str, Any]], meal_role: str, actions: list[dict[str, Any]]) -> bool:
    target_slot = "lunch" if meal_role == "lunch" else "evening"
    target_time = "12:45" if meal_role == "lunch" else "19:00"
    for day in itinerary_days:
        for item in day.get("items") or []:
            if item.get("itemKind") == "gap":
                continue
            if not _is_meal_like_item(item):
                continue
            item["time_slot"] = target_slot
            item["start_time"] = target_time
            item["slotLockReason"] = f"agent_replanner_{meal_role}_timing"
            if meal_role == "dinner":
                item.setdefault("role", "dinner")
            else:
                item.setdefault("role", "lunch")
            actions.append({"type": f"repair_{meal_role}_timing", "target": _item_label(item), "slot": target_slot})
            return True
    return False


def _ensure_meal_stop(
    day: dict[str, Any],
    meal_role: str,
    actions: list[dict[str, Any]],
    planning_brief: dict[str, Any] | None = None,
) -> bool:
    target_slot = "lunch" if meal_role == "lunch" else "evening"
    target_time = "12:45" if meal_role == "lunch" else "19:00"
    preferred_query = MEAL_TARGETS["brunch"][0] if meal_role == "lunch" else MEAL_TARGETS["french_dinner"][0]

    for item in day.get("items") or []:
        if item.get("itemKind") == "gap" or item.get("finalAnchor"):
            continue
        category = str((item.get("place") or {}).get("category") or "").lower()
        if category not in MEAL_CATEGORIES:
            continue
        item["role"] = meal_role
        item["isMeal"] = True
        item["time_slot"] = target_slot
        item["start_time"] = target_time
        item["slotLockReason"] = f"agent_replanner_insert_{meal_role}"
        place = item.setdefault("place", {})
        place["role"] = meal_role
        place["is_meal"] = True
        if meal_role == "dinner":
            item["description"] = f"{_item_label(item)} is positioned in the evening so the day closes with a proper dinner stop."
        else:
            item["description"] = f"{_item_label(item)} is placed around midday so the day has a sustainable lunch break."
        actions.append({"type": f"ensure_{meal_role}", "target": _item_label(item), "slot": target_slot})
        return True

    place = _resolve_target_place(preferred_query)
    if place is None:
        return False

    items = list(day.get("items") or [])
    item_limit = _day_item_limit(planning_brief or {}, day) if planning_brief is not None else 5
    if len([item for item in items if item.get("itemKind") != "gap"]) >= item_limit:
        remove_index = _meal_heavy_remove_index(items, [])
        if remove_index is not None:
            removed = items.pop(remove_index)
            actions.append({"type": f"swap_for_{meal_role}", "target": _item_label(removed)})

    inserted = _item_from_place(
        place,
        day_number=int(day.get("day_number") or 1),
        index=len(items) + 1,
        slot=target_slot,
    )
    inserted["role"] = meal_role
    inserted["isMeal"] = True
    inserted["time_slot"] = target_slot
    inserted["start_time"] = target_time
    inserted["slotLockReason"] = f"agent_replanner_insert_{meal_role}"
    inserted["place"]["role"] = meal_role
    inserted["place"]["is_meal"] = True
    if meal_role == "dinner":
        inserted["description"] = f"{inserted['title']} closes the day with a proper dinner block near the evening cluster."
    else:
        inserted["description"] = f"{inserted['title']} adds a clear lunch break near the midday activity cluster."
    items.insert(_insert_index_for_slot(items, target_slot), inserted)
    day["items"] = items
    actions.append({"type": f"insert_{meal_role}", "target": inserted["title"], "slot": target_slot})
    return True


def _ensure_default_main_activity(
    itinerary_days: list[dict[str, Any]],
    planning_brief: dict[str, Any],
    actions: list[dict[str, Any]],
    *,
    prefer_art: bool,
) -> bool:
    changed = False
    preferred_targets = [str(value) for value in planning_brief.get("must_include") or [] if str(value).strip()]
    fallback_targets = preferred_targets[:]
    if prefer_art:
        fallback_targets.extend(["Louvre Museum", "Musee d'Orsay"])
    fallback_targets.extend(["Palais Royal", "Arc de Triomphe"])

    for day in itinerary_days:
        day_items = [item for item in day.get("items") or [] if item.get("itemKind") != "gap"]
        if any(_is_main_activity_item(item) for item in day_items):
            continue
        inserted_place = None
        for target in dict.fromkeys(fallback_targets):
            inserted_place = _resolve_target_place(target)
            if inserted_place:
                break
        if inserted_place is None:
            continue
        items = list(day.get("items") or [])
        if len(day_items) >= _day_item_limit(planning_brief, day):
            remove_index = _meal_heavy_remove_index(items, preferred_targets)
            if remove_index is not None:
                removed = items.pop(remove_index)
                actions.append({"type": "swap_for_main_activity", "target": _item_label(removed)})
        inserted = _item_from_place(
            inserted_place,
            day_number=int(day.get("day_number") or 1),
            index=len(items) + 1,
            slot="morning",
        )
        inserted["role"] = "museum_or_gallery" if prefer_art else "main_activity"
        inserted["place"]["role"] = inserted["role"]
        inserted["place"]["is_main_activity"] = True
        inserted["place"]["is_art_or_culture"] = prefer_art or bool(inserted["place"].get("is_art_or_culture"))
        items.insert(0, inserted)
        day["items"] = items
        actions.append({"type": "insert_main_activity", "target": _item_label(inserted), "prefer_art": prefer_art})
        changed = True
    return changed


def _reduce_repetitive_category_run(itinerary_days: list[dict[str, Any]], actions: list[dict[str, Any]]) -> bool:
    changed = False
    for day in itinerary_days:
        items = list(day.get("items") or [])
        previous_category = ""
        run_count = 0
        next_items: list[dict[str, Any]] = []
        for item in items:
            if item.get("itemKind") == "gap":
                next_items.append(item)
                continue
            category = str((item.get("place") or {}).get("category") or "").lower()
            if category == previous_category:
                run_count += 1
            else:
                previous_category = category
                run_count = 1
            if run_count > 2 and not item.get("finalAnchor"):
                actions.append({"type": "trim_repetitive_category", "target": _item_label(item), "category": category})
                changed = True
                continue
            next_items.append(item)
        day["items"] = next_items
    return changed


def _ensure_role_diversity(
    day: dict[str, Any],
    planning_brief: dict[str, Any],
    actions: list[dict[str, Any]],
) -> bool:
    changed = False
    changed = _break_consecutive_meal_runs(day, planning_brief, actions) or changed
    changed = _reduce_repetitive_category_run([day], actions) or changed
    changed = _reduce_excess_cafes([day], actions) or changed

    roles = _day_roles(day)
    if "dinner" not in roles:
        changed = _ensure_meal_stop(day, "dinner", actions, planning_brief) or changed
        roles = _day_roles(day)
    if (len(roles) < 3 or _day_category_count(day) < 3) and "walking_route" not in roles:
        changed = _ensure_supporting_walk_stop(day, actions, planning_brief) or changed
        roles = _day_roles(day)
    if (
        _day_category_count(day) < 3
        and not any(role in roles for role in {"cafe_break", "dessert"})
        and "cafe" in _concepts_from_brief(planning_brief)
    ):
        changed = _ensure_cafe_support_stop(day, actions, planning_brief) or changed
        roles = _day_roles(day)
    if len(roles) < 3 and not any(role in roles for role in {"main_activity", "museum_or_gallery", "landmark", "shopping"}):
        changed = _ensure_default_main_activity([day], planning_brief, actions, prefer_art=False) or changed
    return changed


def _break_consecutive_meal_runs(
    day: dict[str, Any],
    planning_brief: dict[str, Any],
    actions: list[dict[str, Any]],
) -> bool:
    items = list(day.get("items") or [])
    hard_targets = [str(value) for value in planning_brief.get("must_include") or [] if str(value).strip()]
    real_indices = [index for index, item in enumerate(items) if item.get("itemKind") != "gap"]
    changed = False

    for current_index, next_index in zip(real_indices, real_indices[1:]):
        current = items[current_index]
        next_item = items[next_index]
        if not (_is_meal_like_item(current) and _is_meal_like_item(next_item)):
            continue

        current_role = str(current.get("role") or ((current.get("place") or {}).get("role") or "")).lower()
        next_role = str(next_item.get("role") or ((next_item.get("place") or {}).get("role") or "")).lower()
        duplicate_meal_role = current_role == next_role and current_role in {"lunch", "dinner"}
        current_protected = current.get("finalAnchor") or any(_matches_target(current, target) for target in hard_targets)
        next_protected = next_item.get("finalAnchor") or any(_matches_target(next_item, target) for target in hard_targets)

        if duplicate_meal_role and not next_protected:
            removed = items.pop(next_index)
            actions.append({"type": "remove_duplicate_meal_block", "target": _item_label(removed)})
            day["items"] = items
            return True
        if duplicate_meal_role and not current_protected:
            removed = items.pop(current_index)
            actions.append({"type": "remove_duplicate_meal_block", "target": _item_label(removed)})
            day["items"] = items
            return True

        item_limit = _day_item_limit(planning_brief, day)
        real_item_count = len([item for item in items if item.get("itemKind") != "gap"])
        if real_item_count < item_limit:
            place = _resolve_target_place("Seine River Walk") or _resolve_target_place("Luxembourg Gardens")
            if place is not None:
                inserted = _item_from_place(
                    place,
                    day_number=int(day.get("day_number") or 1),
                    index=len(items) + 1,
                    slot="afternoon",
                )
                inserted["role"] = "walking_route"
                inserted["place"]["role"] = "walking_route"
                inserted["place"]["is_main_activity"] = False
                previous_minutes = _item_minutes(current)
                next_minutes = _item_minutes(next_item)
                bridge_minutes = previous_minutes + max(45, min(120, (max(next_minutes - previous_minutes, 90) // 2)))
                if next_minutes > previous_minutes:
                    bridge_minutes = min(bridge_minutes, max(previous_minutes + 30, next_minutes - 30))
                inserted["start_time"] = _format_minutes(bridge_minutes)
                inserted["time_slot"] = _slot_from_minutes(bridge_minutes)
                inserted["description"] = (
                    f"{inserted['title']} breaks up the meal sequence so {_item_label(current)} "
                    f"and {_item_label(next_item)} do not collapse into the same rhythm."
                )
                items.insert(next_index, inserted)
                day["items"] = items
                actions.append(
                    {
                        "type": "insert_walk_between_meals",
                        "target": inserted["title"],
                        "between": [_item_label(current), _item_label(next_item)],
                    }
                )
                return True

        if not next_protected:
            removed = items.pop(next_index)
            actions.append({"type": "remove_consecutive_meal_block", "target": _item_label(removed)})
            day["items"] = items
            return True
        if not current_protected:
            removed = items.pop(current_index)
            actions.append({"type": "remove_consecutive_meal_block", "target": _item_label(removed)})
            day["items"] = items
            return True

    return changed


def _ensure_recovery_stop(
    day: dict[str, Any],
    actions: list[dict[str, Any]],
    planning_brief: dict[str, Any] | None = None,
) -> bool:
    items = list(day.get("items") or [])
    hard_targets = [str(value) for value in (planning_brief or {}).get("must_include") or [] if str(value).strip()]
    real_indices = [index for index, item in enumerate(items) if item.get("itemKind") != "gap"]
    if len(real_indices) < 2:
        return False

    prefer_cafe = _brief_prefers_indoor_recovery(planning_brief or {})
    for current_index, next_index in zip(real_indices, real_indices[1:]):
        current = items[current_index]
        next_item = items[next_index]
        if not (_is_high_intensity_recovery_item(current) and _is_high_intensity_recovery_item(next_item)):
            continue

        recovery_place = _resolve_target_place("Fika") or _resolve_target_place("L'ombre de Notre-Dame")
        recovery_role = "cafe_break"
        if recovery_place is None or not prefer_cafe:
            recovery_place = _resolve_target_place("Seine River Walk") or _resolve_target_place("Luxembourg Gardens")
            recovery_role = "walking_route"
        if recovery_place is None:
            return False

        current_minutes = _item_minutes(current)
        next_minutes = _item_minutes(next_item)
        midpoint = current_minutes + max(35, min(90, (max(next_minutes - current_minutes, 90) // 2)))
        if next_minutes > current_minutes:
            midpoint = min(midpoint, max(current_minutes + 30, next_minutes - 20))
        slot = _slot_from_minutes(midpoint)
        inserted = _item_from_place(
            recovery_place,
            day_number=int(day.get("day_number") or 1),
            index=len(items) + 1,
            slot=slot,
        )
        inserted["role"] = recovery_role
        inserted["time_slot"] = slot
        inserted["start_time"] = _format_minutes(midpoint)
        inserted["place"]["role"] = recovery_role
        inserted["place"]["is_main_activity"] = False
        inserted["place"]["is_cafe"] = recovery_role == "cafe_break"
        inserted["place"]["is_meal"] = False
        if recovery_role == "cafe_break":
            inserted["description"] = (
                f"{inserted['title']} is placed between {_item_label(current)} and {_item_label(next_item)} "
                "so the day can recover before the next heavy cultural block."
            )
        else:
            inserted["description"] = (
                f"{inserted['title']} breaks up {_item_label(current)} and {_item_label(next_item)} "
                "with a lighter walking beat before the next major stop."
            )

        real_item_count = len(real_indices)
        item_limit = _day_item_limit(planning_brief or {}, day) if planning_brief is not None else 5
        current_protected = current.get("finalAnchor") or any(_matches_target(current, target) for target in hard_targets)
        next_protected = next_item.get("finalAnchor") or any(_matches_target(next_item, target) for target in hard_targets)

        if real_item_count < item_limit:
            items.insert(next_index, inserted)
            day["items"] = items
            actions.append(
                {
                    "type": "insert_recovery_stop",
                    "target": inserted["title"],
                    "between": [_item_label(current), _item_label(next_item)],
                    "role": recovery_role,
                }
            )
            return True

        replace_index = None
        if not next_protected:
            replace_index = next_index
        elif not current_protected:
            replace_index = current_index
        if replace_index is None:
            continue

        replaced = items[replace_index]
        items[replace_index] = inserted
        day["items"] = items
        actions.append(
            {
                "type": "swap_for_recovery_stop",
                "target": inserted["title"],
                "replaced": _item_label(replaced),
                "between": [_item_label(current), _item_label(next_item)],
                "role": recovery_role,
            }
        )
        return True

    return _ensure_supporting_walk_stop(day, actions, planning_brief)


def _ensure_supporting_walk_stop(
    day: dict[str, Any],
    actions: list[dict[str, Any]],
    planning_brief: dict[str, Any] | None = None,
) -> bool:
    if "walking_route" in _day_roles(day):
        return False
    place = _resolve_target_place("Seine River Walk") or _resolve_target_place("Luxembourg Gardens")
    if place is None:
        return False
    items = list(day.get("items") or [])
    item_limit = _day_item_limit(planning_brief or {}, day) if planning_brief is not None else 5
    if len([item for item in items if item.get("itemKind") != "gap"]) >= item_limit:
        remove_index = _meal_heavy_remove_index(items, [])
        if remove_index is not None:
            removed = items.pop(remove_index)
            actions.append({"type": "swap_for_walk_stop", "target": _item_label(removed)})
    inserted = _item_from_place(
        place,
        day_number=int(day.get("day_number") or 1),
        index=len(items) + 1,
        slot="afternoon",
    )
    inserted["role"] = "walking_route"
    inserted["place"]["role"] = "walking_route"
    inserted["place"]["is_main_activity"] = False
    inserted["description"] = f"{inserted['title']} links nearby stops so the day gains a natural walk instead of another repetitive indoor block."
    items.insert(_insert_index_for_slot(items, "afternoon"), inserted)
    day["items"] = items
    actions.append({"type": "insert_walk_stop", "target": inserted["title"], "slot": "afternoon"})
    return True


def _append_evening_walk_stop(
    day: dict[str, Any],
    actions: list[dict[str, Any]],
    planning_brief: dict[str, Any] | None = None,
) -> bool:
    items = [item for item in day.get("items") or [] if item.get("itemKind") != "gap"]
    if not items:
        return False
    tail = items[-1]
    tail_role = str(tail.get("role") or ((tail.get("place") or {}).get("role") or "")).lower()
    if tail_role in {"walking_route", "night_activity", "dinner"} or bool(tail.get("isNightViewSpot")):
        return False
    place = _resolve_target_place("Seine River Walk") or _resolve_target_place("Luxembourg Gardens")
    if place is None:
        return False
    all_items = list(day.get("items") or [])
    item_limit = _day_item_limit(planning_brief or {}, day) if planning_brief is not None else 5
    if len([item for item in all_items if item.get("itemKind") != "gap"]) >= item_limit:
        remove_index = _meal_heavy_remove_index(all_items, [])
        if remove_index is not None:
            removed = all_items.pop(remove_index)
            actions.append({"type": "swap_for_evening_walk_stop", "target": _item_label(removed)})
    inserted = _item_from_place(
        place,
        day_number=int(day.get("day_number") or 1),
        index=len(all_items) + 1,
        slot="evening",
    )
    inserted["role"] = "walking_route"
    inserted["time_slot"] = "evening"
    inserted["start_time"] = "20:15"
    inserted["place"]["role"] = "walking_route"
    inserted["place"]["is_main_activity"] = False
    inserted["description"] = f"{inserted['title']} gives the day a softer evening landing instead of ending on another heavy stop."
    final_index = next((index for index, item in enumerate(all_items) if item.get("finalAnchor")), None)
    insert_index = final_index if final_index is not None else len(all_items)
    all_items.insert(insert_index, inserted)
    day["items"] = all_items
    actions.append({"type": "append_evening_walk_stop", "target": inserted["title"], "slot": "evening"})
    return True


def _concepts_from_brief(planning_brief: dict[str, Any], target: str = "") -> list[str]:
    concepts: list[str] = []
    values = [
        *[str(value) for value in planning_brief.get("travel_style") or [] if str(value).strip()],
        *[str(value) for value in planning_brief.get("meal_preference") or [] if str(value).strip()],
        str(planning_brief.get("source_text") or ""),
        str(target or ""),
    ]
    joined = " ".join(values).lower()

    def include(name: str, *tokens: str) -> None:
        if name in concepts:
            return
        if any(token in joined for token in tokens):
            concepts.append(name)

    include("romantic", "romantic", "romance", "데이트", "기념일", "커플", "couple")
    include("landmark", "landmark", "classic", "관광지", "명소", "history", "architecture")
    include("art", "museum", "gallery", "art", "culture", "미술관", "박물관", "예술")
    include("shopping", "shopping", "쇼핑")
    include("local", "local", "로컬", "현지", "골목", "동네", "quiet", "조용")
    include("night_view", "night_view", "nightview", "야경", "sunset", "노을")
    include("foodie", "foodie", "맛집", "미식", "restaurant", "식당", "레스토랑", "french", "bistro", "brasserie")
    include("cafe", "cafe", "coffee", "dessert", "bakery", "카페", "커피", "디저트")
    include("family", "family", "가족", "아이", "kids", "children")
    return concepts


def _day_has_concept(day: dict[str, Any], concept: str) -> bool:
    items = [item for item in day.get("items") or [] if item.get("itemKind") != "gap"]
    if concept == "art":
        return any(_is_museum_item(item) for item in items)
    if concept == "shopping":
        return any(str(item.get("role") or "").lower() == "shopping" or str((item.get("place") or {}).get("category") or "").lower() == "shopping" for item in items)
    if concept == "local":
        return any(str(item.get("role") or "").lower() == "walking_route" or str((item.get("place") or {}).get("category") or "").lower() in {"neighborhood", "park"} for item in items)
    if concept == "cafe":
        return any(_is_cafe_like_item(item) for item in items)
    if concept == "foodie":
        return any(_is_meal_like_item(item) for item in items)
    if concept == "romantic":
        return any(bool(item.get("isNightViewSpot")) for item in items) or ("dinner" in _day_roles(day) and "walking_route" in _day_roles(day))
    if concept == "night_view":
        return any(bool(item.get("isNightViewSpot")) or (str(item.get("role") or "").lower() == "landmark" and str(item.get("time_slot") or "") in {"evening", "night"}) for item in items)
    if concept == "landmark":
        return any(_is_main_activity_item(item) and str((item.get("place") or {}).get("category") or "").lower() in {"landmark", "cathedral", "museum", "gallery"} for item in items)
    if concept == "family":
        return "walking_route" in _day_roles(day) and "dinner" in _day_roles(day)
    return False


def _ensure_cafe_support_stop(
    day: dict[str, Any],
    actions: list[dict[str, Any]],
    planning_brief: dict[str, Any] | None = None,
) -> bool:
    if _day_has_concept(day, "cafe"):
        return False
    place = _resolve_target_place("Fika") or _resolve_target_place("L'ombre de Notre-Dame")
    if place is None:
        return False
    items = list(day.get("items") or [])
    item_limit = _day_item_limit(planning_brief or {}, day) if planning_brief is not None else 5
    if len([item for item in items if item.get("itemKind") != "gap"]) >= item_limit:
        remove_index = _meal_heavy_remove_index(items, [])
        if remove_index is not None:
            removed = items.pop(remove_index)
            actions.append({"type": "swap_for_cafe_support", "target": _item_label(removed)})
    inserted = _item_from_place(
        place,
        day_number=int(day.get("day_number") or 1),
        index=len(items) + 1,
        slot="afternoon",
    )
    inserted["role"] = "cafe_break"
    inserted["place"]["role"] = "cafe_break"
    inserted["place"]["is_cafe"] = True
    inserted["description"] = f"{inserted['title']} adds a lighter cafe beat so the day reflects the requested mood more clearly."
    items.insert(_insert_index_for_slot(items, "afternoon"), inserted)
    day["items"] = items
    actions.append({"type": "insert_cafe_support", "target": inserted["title"], "slot": "afternoon"})
    return True


def _ensure_shopping_support_stop(
    day: dict[str, Any],
    actions: list[dict[str, Any]],
    planning_brief: dict[str, Any] | None = None,
) -> bool:
    if _day_has_concept(day, "shopping"):
        return False
    place = _resolve_target_place("Galeries Lafayette") or _resolve_target_place("Champs Elysees")
    if place is None:
        return False
    items = list(day.get("items") or [])
    item_limit = _day_item_limit(planning_brief or {}, day) if planning_brief is not None else 5
    if len([item for item in items if item.get("itemKind") != "gap"]) >= item_limit:
        remove_index = _meal_heavy_remove_index(items, [])
        if remove_index is not None:
            removed = items.pop(remove_index)
            actions.append({"type": "swap_for_shopping_support", "target": _item_label(removed)})
    inserted = _item_from_place(
        place,
        day_number=int(day.get("day_number") or 1),
        index=len(items) + 1,
        slot="afternoon",
    )
    inserted["role"] = "shopping"
    inserted["place"]["role"] = "shopping"
    inserted["place"]["is_main_activity"] = True
    inserted["description"] = f"{inserted['title']} restores a visible shopping block so the day matches the requested trip concept."
    items.insert(_insert_index_for_slot(items, "afternoon"), inserted)
    day["items"] = items
    actions.append({"type": "insert_shopping_support", "target": inserted["title"], "slot": "afternoon"})
    return True


def _rebalance_requested_concepts(
    itinerary_days: list[dict[str, Any]],
    planning_brief: dict[str, Any],
    target: str,
    actions: list[dict[str, Any]],
) -> bool:
    concepts = _concepts_from_brief(planning_brief, target)
    if not concepts or not itinerary_days:
        return False
    changed = False
    for concept in concepts:
        if concept == "art":
            candidate_day = next((day for day in itinerary_days if not _day_has_concept(day, concept)), itinerary_days[0])
            changed = _ensure_default_main_activity([candidate_day], planning_brief, actions, prefer_art=True) or changed
        elif concept == "shopping":
            candidate_day = next((day for day in itinerary_days if not _day_has_concept(day, concept)), itinerary_days[-1])
            changed = _ensure_shopping_support_stop(candidate_day, actions, planning_brief) or changed
        elif concept == "local":
            candidate_day = next((day for day in itinerary_days if not _day_has_concept(day, concept)), itinerary_days[0])
            changed = _ensure_supporting_walk_stop(candidate_day, actions, planning_brief) or changed
        elif concept == "cafe":
            candidate_day = next((day for day in itinerary_days if not _day_has_concept(day, concept)), itinerary_days[0])
            changed = _ensure_cafe_support_stop(candidate_day, actions, planning_brief) or changed
        elif concept == "foodie":
            candidate_day = next((day for day in itinerary_days if not _day_has_concept(day, concept)), itinerary_days[-1])
            changed = _ensure_meal_stop(candidate_day, "dinner", actions, planning_brief) or changed
        elif concept == "romantic":
            candidate_day = next((day for day in reversed(itinerary_days) if not _day_has_concept(day, concept)), itinerary_days[-1])
            changed = _ensure_meal_stop(candidate_day, "dinner", actions, planning_brief) or changed
            changed = _append_evening_walk_stop(candidate_day, actions, planning_brief) or changed
        elif concept == "night_view":
            candidate_day = next((day for day in reversed(itinerary_days) if not _day_has_concept(day, concept)), itinerary_days[-1])
            changed = _ensure_target_present([candidate_day], "에펠탑", planning_brief, actions) or changed
            changed = _append_evening_walk_stop(candidate_day, actions, planning_brief) or changed
        elif concept == "landmark":
            candidate_day = next((day for day in itinerary_days if not _day_has_concept(day, concept)), itinerary_days[0])
            changed = _ensure_default_main_activity([candidate_day], planning_brief, actions, prefer_art=False) or changed
        elif concept == "family":
            candidate_day = next((day for day in itinerary_days if not _day_has_concept(day, concept)), itinerary_days[0])
            changed = _remove_family_unsuitable_items(candidate_day, planning_brief, actions) or changed
            changed = _ensure_supporting_walk_stop(candidate_day, actions, planning_brief) or changed
            changed = _ensure_meal_stop(candidate_day, "dinner", actions, planning_brief) or changed
    return changed


def _rebalance_day_density(
    day: dict[str, Any],
    planning_brief: dict[str, Any],
    actions: list[dict[str, Any]],
) -> bool:
    pace = str(planning_brief.get("pace") or "normal").lower()
    items = [item for item in day.get("items") or [] if item.get("itemKind") != "gap"]
    if not items:
        return False
    minimum, maximum = (3, _day_item_limit(planning_brief, day)) if pace == "slow" else (7, 9) if pace in {"fast", "packed"} else (5, 7)
    changed = False
    all_items = list(day.get("items") or [])
    while len([item for item in all_items if item.get("itemKind") != "gap"]) > maximum:
        remove_index = _low_priority_remove_index(all_items, [str(value) for value in planning_brief.get("must_include") or [] if str(value).strip()])
        if remove_index is None:
            break
        removed = all_items.pop(remove_index)
        actions.append({"type": "trim_for_pace_density", "target": _item_label(removed), "pace": pace})
        changed = True
    day["items"] = all_items
    if len([item for item in all_items if item.get("itemKind") != "gap"]) < minimum:
        if _day_roles(day).isdisjoint({"main_activity", "museum_or_gallery", "landmark", "shopping"}):
            changed = _ensure_default_main_activity([day], planning_brief, actions, prefer_art=False) or changed
        if len([item for item in day.get("items") or [] if item.get("itemKind") != "gap"]) < minimum:
            changed = _ensure_supporting_walk_stop(day, actions, planning_brief) or changed
        if pace in {"fast", "packed"} and len([item for item in day.get("items") or [] if item.get("itemKind") != "gap"]) < minimum:
            changed = _append_evening_walk_stop(day, actions, planning_brief) or changed
    return changed


def _soften_night_tail(
    day: dict[str, Any],
    actions: list[dict[str, Any]],
    planning_brief: dict[str, Any] | None = None,
) -> bool:
    items = [item for item in day.get("items") or [] if item.get("itemKind") != "gap"]
    if not items:
        return False
    tail = items[-1]
    tail_role = str(tail.get("role") or ((tail.get("place") or {}).get("role") or "")).lower()
    tail_category = str((tail.get("place") or {}).get("category") or "").lower()
    if tail_role in {"walking_route", "night_activity", "dinner"} or bool(tail.get("isNightViewSpot")):
        return False
    changed = False
    if tail_category in {"museum", "gallery", "shopping"} and not tail.get("finalAnchor"):
        tail["time_slot"] = "afternoon"
        tail["start_time"] = "16:30"
        tail["slotLockReason"] = "agent_replanner_soften_night_tail"
        actions.append({"type": "retime_heavy_night_tail", "target": _item_label(tail), "slot": "afternoon"})
        changed = True
    changed = _ensure_meal_stop(day, "dinner", actions, planning_brief) or changed
    changed = _append_evening_walk_stop(day, actions, planning_brief) or changed
    return changed


def _rewrite_day_theme(itinerary_days: list[dict[str, Any]], actions: list[dict[str, Any]]) -> bool:
    changed = False
    for day in itinerary_days:
        items = [item for item in day.get("items") or [] if item.get("itemKind") != "gap"]
        if not items:
            continue
        lead = next((item for item in items if _is_main_activity_item(item)), items[0])
        ending = next((item for item in reversed(items) if item.get("role") in {"dinner", "night_activity", "walking_route"}), items[-1])
        lead_name = _item_label(lead)
        ending_name = _item_label(ending)
        new_theme = f"{lead_name} to {ending_name}"
        if str(day.get("title") or "") == new_theme and str(day.get("theme") or "") == new_theme and str(day.get("dayTheme") or "") == new_theme:
            continue
        day["title"] = new_theme
        day["theme"] = new_theme
        day["dayTheme"] = new_theme
        actions.append({"type": "rewrite_day_theme", "day": day.get("day_number"), "title": new_theme})
        changed = True
    return changed


def _rewrite_item_descriptions(itinerary_days: list[dict[str, Any]], actions: list[dict[str, Any]]) -> bool:
    changed = False
    for day in itinerary_days:
        day_changed = False
        items = [item for item in day.get("items") or [] if item.get("itemKind") != "gap"]
        for index, item in enumerate(items):
            if item.get("itemKind") == "gap":
                continue
            place = item.get("place") or {}
            area = str(place.get("neighborhood") or place.get("location") or "").strip()
            slot = str(item.get("time_slot") or "afternoon")
            role = str(item.get("role") or place.get("role") or "stop")
            title = _item_label(item)
            previous_title = _item_label(items[index - 1]) if index > 0 else ""
            next_title = _item_label(items[index + 1]) if index + 1 < len(items) else ""
            area_text = f" around {area}" if area else ""
            if role in {"dinner", "lunch"}:
                if previous_title and next_title:
                    description = (
                        f"{title} lands in the {slot} block{area_text}, giving the route a real meal stop "
                        f"between {previous_title} and {next_title}."
                    )
                elif previous_title:
                    description = (
                        f"{title} follows {previous_title}{area_text} so the day gets a proper {role} break "
                        f"instead of stretching without a pause."
                    )
                else:
                    description = f"{title} sets a clear {role} stop in the {slot} window{area_text} so the day has a proper reset."
            elif role == "cafe_break":
                if next_title:
                    description = (
                        f"{title} adds a short cafe beat{area_text} before {next_title}, keeping the next block from feeling abrupt."
                    )
                else:
                    description = f"{title} adds a short cafe beat{area_text} so the day ends with a lighter pause."
            elif role == "walking_route":
                if previous_title and next_title:
                    description = (
                        f"{title} creates a walkable bridge{area_text} from {previous_title} to {next_title}, "
                        f"so the route changes pace without a hard jump."
                    )
                elif next_title:
                    description = f"{title} opens the route{area_text} before {next_title}, easing into the stronger anchor ahead."
                elif previous_title:
                    description = (
                        f"{title} lets the day breathe after {previous_title}{area_text}, "
                        f"so the route can ease out instead of ending on another hard stop."
                    )
                else:
                    description = f"{title} keeps the route human-scaled{area_text} so the day closes without another hard stop."
            elif role in {"museum_or_gallery", "main_activity", "landmark", "shopping"}:
                if next_title:
                    description = (
                        f"{title} gives the {slot} stretch{area_text} its clearest focal point, with {next_title} carrying the route onward."
                    )
                elif previous_title:
                    description = (
                        f"{title} becomes the payoff after {previous_title}{area_text}, so the day still has a strong anchor near the end."
                    )
                else:
                    description = f"{title} anchors the {slot} block{area_text} so this part of the day has a clear purpose."
            else:
                if previous_title and next_title:
                    description = (
                        f"{title} supports the {slot} sequence{area_text} between {previous_title} and {next_title} without forcing a detour."
                    )
                else:
                    description = f"{title} supports the {slot} sequence{area_text} without forcing a detour."
            if str(item.get("description") or "").strip() == description:
                continue
            item["description"] = description
            day_changed = True
            changed = True
        if day_changed:
            actions.append({"type": "rewrite_item_descriptions", "day": day.get("day_number")})
    return changed


def _day_roles(day: dict[str, Any]) -> set[str]:
    roles: set[str] = set()
    for item in day.get("items") or []:
        if item.get("itemKind") == "gap":
            continue
        role = str(item.get("role") or ((item.get("place") or {}).get("role") or "")).strip()
        if role:
            roles.add(role)
    return roles


def _day_category_count(day: dict[str, Any]) -> int:
    return len(
        {
            str((item.get("place") or {}).get("category") or "").strip().lower()
            for item in day.get("items") or []
            if item.get("itemKind") != "gap" and str((item.get("place") or {}).get("category") or "").strip()
        }
    )


def _trim_for_story_quality(
    itinerary_days: list[dict[str, Any]],
    planning_brief: dict[str, Any],
    actions: list[dict[str, Any]],
) -> bool:
    hard_targets = [str(value) for value in planning_brief.get("must_include") or [] if str(value).strip()]
    changed = False
    for day in itinerary_days:
        items = list(day.get("items") or [])
        limit = _day_item_limit(planning_brief, day) if str(planning_brief.get("pace") or "").lower() == "slow" else 5
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


def _is_cafe_like_item(item: dict[str, Any]) -> bool:
    role = str(item.get("role") or ((item.get("place") or {}).get("role") or "")).lower()
    category = str((item.get("place") or {}).get("category") or "").lower()
    return role in {"cafe_break", "dessert"} or category in {"cafe", "bakery"}


def _is_meal_like_item(item: dict[str, Any]) -> bool:
    role = str(item.get("role") or ((item.get("place") or {}).get("role") or "")).lower()
    category = str((item.get("place") or {}).get("category") or "").lower()
    return bool(item.get("isMeal")) or role in {"lunch", "dinner", "dessert", "night_activity"} or category in MEAL_CATEGORIES


def _brief_prefers_indoor_recovery(planning_brief: dict[str, Any]) -> bool:
    tokens = _normalized_style_tokens(planning_brief)
    source_text = _normalize(str(planning_brief.get("source_text") or ""))
    return bool(tokens.intersection({"indoor", "museum", "art", "culture", "rainy"})) or any(
        token in source_text for token in ("실내", "비오는", "비오는날", "rain", "rainy")
    )


def _is_high_intensity_recovery_item(item: dict[str, Any]) -> bool:
    if _is_meal_like_item(item) or _is_cafe_like_item(item) or _is_walk_like_item(item):
        return False
    category = str((item.get("place") or {}).get("category") or "").lower()
    return category in {"museum", "gallery", "landmark", "cathedral", "shopping"} or _is_main_activity_item(item)


def _is_main_activity_item(item: dict[str, Any]) -> bool:
    role = str(item.get("role") or ((item.get("place") or {}).get("role") or "")).lower()
    category = str((item.get("place") or {}).get("category") or "").lower()
    return role in {"main_activity", "museum_or_gallery", "landmark", "shopping"} or category in {"museum", "gallery", "landmark", "cathedral", "shopping"}


def _is_tourist_heavy_item(item: dict[str, Any]) -> bool:
    category = str((item.get("place") or {}).get("category") or "").lower()
    return category in {"museum", "gallery", "landmark", "cathedral", "shopping"}


def _meal_like_ratio(items: list[dict[str, Any]]) -> float:
    real_items = [item for item in items if item.get("itemKind") != "gap"]
    if not real_items:
        return 0.0
    return sum(1 for item in real_items if _is_meal_like_item(item)) / len(real_items)


def _meal_heavy_remove_index(items: list[dict[str, Any]], hard_targets: list[str]) -> int | None:
    for index in range(len(items) - 1, -1, -1):
        item = items[index]
        if item.get("itemKind") == "gap" or item.get("finalAnchor"):
            continue
        if any(_matches_target(item, target) for target in hard_targets):
            continue
        if _is_cafe_like_item(item):
            return index
    for index in range(len(items) - 1, -1, -1):
        item = items[index]
        if item.get("itemKind") == "gap" or item.get("finalAnchor"):
            continue
        if any(_matches_target(item, target) for target in hard_targets):
            continue
        if _is_meal_like_item(item):
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
    role = "museum_or_gallery" if str(place.get("category") or "").lower() in {"museum", "gallery"} else "dinner" if normalized_slot == "evening" and str(place.get("category") or "").lower() in MEAL_CATEGORIES else "lunch" if normalized_slot == "lunch" and str(place.get("category") or "").lower() in MEAL_CATEGORIES else "cafe_break" if str(place.get("category") or "").lower() in {"cafe", "bakery"} else "walking_route" if str(place.get("category") or "").lower() in {"park", "neighborhood"} else "landmark" if str(place.get("category") or "").lower() in {"landmark", "cathedral"} else "main_activity"
    return {
        "id": f"{day_number}-{place.get('slug') or 'agent-place'}-{index}",
        "time_slot": normalized_slot,
        "start_time": SLOT_START_TIMES.get(slot, SLOT_START_TIMES.get(normalized_slot, "15:00")),
        "role": role,
        "title": place.get("name") or "Paris stop",
        "place": {
            "place_id": place.get("slug") or place.get("place_id"),
            "name": place.get("name") or "Paris stop",
            "coordinates": dict(place.get("coordinates") or {"lat": 48.8566, "lng": 2.3522}),
            "category": place.get("category") or "landmark",
            "role": role,
            "experience_type": "art_culture" if role == "museum_or_gallery" else "dining" if role in {"lunch", "dinner"} else "coffee_break" if role == "cafe_break" else "local_walk" if role == "walking_route" else "main_activity",
            "recommended_duration_min": 90,
            "best_time": [normalized_slot],
            "is_main_activity": role in {"main_activity", "museum_or_gallery", "landmark"},
            "is_meal": role in {"lunch", "dinner"},
            "is_cafe": role == "cafe_break",
            "is_art_or_culture": role == "museum_or_gallery",
            "neighborhood": place.get("location"),
            "lat": (place.get("coordinates") or {}).get("lat"),
            "lng": (place.get("coordinates") or {}).get("lng"),
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
    *,
    reverse: bool = False,
) -> tuple[dict[str, Any], int, dict[str, Any]] | None:
    day_iterable = reversed(itinerary_days) if reverse else itinerary_days
    for day in day_iterable:
        items = list(day.get("items") or [])
        item_iterable = reversed(list(enumerate(items))) if reverse else enumerate(items)
        for index, item in item_iterable:
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
