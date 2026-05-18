from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.core import failure_types as ft
from app.schemas.evaluation_schema import PlanEvaluationResult, PlanFailure
from app.services.planning_brief_service import validate_planning_brief_compliance


HIGH_SEVERITY_TYPES = {
    "missing_required_anchor",
    "must_avoid_violation",
    "time_slot_mismatch",
    "final_anchor_mismatch",
}

FINAL_TARGET_ALIASES: dict[str, tuple[str, ...]] = {
    "eiffel": ("eiffel", "eiffeltower", "\uc5d0\ud3a0", "\uc5d0\ud3a0\ud0d1"),
    "louvre": ("louvre", "louvremuseum", "\ub8e8\ube0c\ub974"),
    "orsay": ("orsay", "museedorsay", "\uc624\ub974\uc138"),
    "seine": ("seine", "seineriver", "seineriverwalk", "\uc13c\uac15"),
    "notre": ("notre", "notredame", "\ub178\ud2b8\ub974\ub2f4"),
    "sainte": ("sainte", "saintechapelle", "\uc0dd\ud2b8\uc0e4\ud3a0"),
    "arc": ("arc", "arcdetriomphe", "\uac1c\uc120\ubb38"),
    "jazz": ("jazz", "jazzbar", "huchette", "\uc7ac\uc988", "\uc7ac\uc988\ubc14", "\ub974\uce74\ubcf4", "\uce74\ubcf4\ub4dc\ub77c\uc704\uc170\ud2b8", "\uc704\uc170\ud2b8"),
    "montmartre": ("montmartre", "sacrecoeur", "\ubabd\ub9c8\ub974\ud2b8\ub974", "\ubabd\ub9c8\ub974\ud2b8"),
    "marais": ("marais", "lemarais", "\ub9c8\ub808"),
    "tuileries": ("tuileries", "tuileriesgarden", "\ud280\ub974\ub9ac", "\ud290\ub974\ub9ac"),
    "luxembourg": ("luxembourg", "luxembourggardens", "\ub8e9\uc0c1\ubd80\ub974"),
    "garnier": ("garnier", "palaisgarnier", "opera", "\uac00\ub974\ub2c8\uc5d0", "\uc624\ud398\ub77c"),
    "palais_royal": ("palaisroyal", "\ud314\ub808\ub8e8\uc544\uc584"),
}

FINAL_CUES = ("final", "finish", "end", "\ub9c8\uc9c0\ub9c9", "\ub9c8\ubb34\ub9ac", "\ub05d")


def evaluate_plan(
    itinerary_days: list[dict[str, Any]],
    planning_brief: dict[str, Any] | None,
    *,
    prompt: str = "",
    language: str = "ko",
) -> dict[str, Any]:
    """Return an Agent-facing, structured evaluation for a generated itinerary."""

    brief = planning_brief or {}
    legacy = validate_planning_brief_compliance(itinerary_days, brief)
    failures: list[dict[str, Any]] = []
    structured_timed_targets = {
        str(constraint.get("canonical") or "").strip()
        for constraint in brief.get("place_constraints") or []
        if isinstance(constraint, dict)
        and str(constraint.get("intent") or "") != "avoid"
        and str(constraint.get("time_slot") or "").strip()
    }

    for value in legacy.get("missing_must_include") or []:
        failures.append(
            _failure(
                "missing_required_anchor",
                "high",
                f"Required place or anchor is missing: {value}",
                target=str(value),
            )
        )

    for value in legacy.get("included_must_avoid") or []:
        failures.append(
            _failure(
                "must_avoid_violation",
                "high",
                f"Forbidden place appears in the itinerary: {value}",
                target=str(value),
            )
        )

    for value in legacy.get("time_slot_violations") or []:
        failures.append(
            _failure(
                "time_slot_mismatch",
                "high",
                f"Requested time semantics were not satisfied: {value}",
                target=str(value),
            )
        )

    for value in legacy.get("meal_preference_violations") or []:
        failures.append(_meal_failure(str(value)))

    for value in legacy.get("pace_violations") or []:
        failures.append(
            _failure(
                "pace_mismatch",
                "medium",
                f"Itinerary pace does not match the requested pace: {value}",
                target=str(value),
            )
        )

    for value in legacy.get("quality_violations") or []:
        issue_type = "helper_gap_quality" if "helper" in str(value) else "story_flow_issue"
        failures.append(
            _failure(
                issue_type,
                "medium",
                f"Story flow or helper block quality issue: {value}",
                target=str(value),
            )
        )

    duplicate_targets = _duplicate_place_targets(itinerary_days)
    for target in duplicate_targets:
        failures.append(
            _failure(
                "duplicate_place",
                "medium",
                f"Place appears more than once: {target}",
                target=target,
            )
        )
    for target in _duplicate_day_pattern_targets(itinerary_days):
        failures.append(
            _failure(
                "duplicate_day_pattern",
                "high",
                f"Multiple days use the same stop sequence: {target}",
                target=target,
            )
        )

    for target in _low_walking_failures(itinerary_days, brief, prompt):
        failures.append(
            _failure(
                "low_walking_violation",
                "high",
                f"Low-walking request is violated by a long walking block or route leg: {target}",
                target=target,
            )
        )

    for failure in _locked_stop_failures(itinerary_days, brief):
        failures.append(failure)

    failures.extend(_structured_constraint_failures(itinerary_days, brief))
    failures.extend(_raw_constraint_failures(itinerary_days, brief, prompt))

    final_target = str(brief.get("final_anchor") or "").strip() or _requested_final_target(brief, prompt)
    if final_target and not _final_item_matches(itinerary_days, final_target):
        failures.append(
            _failure(
                "final_anchor_mismatch",
                "high",
                f"Requested final anchor was not used as the final stop: {final_target}",
                target=final_target,
            )
        )
    failures = _dedupe_failures(failures)

    route_status = _route_status(legacy)
    checks = {
        "must_include": "failed" if legacy.get("missing_must_include") or any(f["type"] == "missing_required_anchor" for f in failures) else "passed",
        "must_avoid": "failed" if legacy.get("included_must_avoid") or any(f["type"] == "must_avoid_violation" for f in failures) else "passed",
        "time_slots": "failed" if legacy.get("time_slot_violations") or any(f["type"] == "time_slot_mismatch" for f in failures) else "passed",
        "route_quality": route_status,
        "pace": "failed" if legacy.get("pace_violations") else "passed",
        "meal_preferences": "failed" if legacy.get("meal_preference_violations") or any(f.get("target") in {"french_dinner", "brunch", "cafe", "jazz_bar"} for f in failures) else "passed",
        "duplicates": "failed" if duplicate_targets else "passed",
        "day_diversity": "failed" if any(f["type"] == "duplicate_day_pattern" for f in failures) else "passed",
        "mobility": "failed" if any(f["type"] == "low_walking_violation" for f in failures) else "passed",
        "final_anchor": "failed" if any(f["type"] == "final_anchor_mismatch" for f in failures) else "passed",
        "ordered_anchors": "failed" if any(f["type"] == "order_mismatch" for f in failures) else "passed",
    }

    base_score = _float_score(legacy.get("final_quality_score") or legacy.get("score"), default=0.0)
    score = _adjusted_score(base_score, failures, checks)
    hard_failures = [failure for failure in failures if failure.get("severity") == "hard"]
    soft_failures = [failure for failure in failures if failure.get("severity") == "soft"]
    passed = bool(legacy.get("is_valid")) and score >= 0.78 and not hard_failures
    evaluation_result = PlanEvaluationResult(
        score=score,
        is_acceptable=passed,
        hard_failures=[_plan_failure_from_dict(failure) for failure in hard_failures],
        soft_failures=[_plan_failure_from_dict(failure) for failure in soft_failures],
        summary="; ".join(_summary_lines(passed, checks, failures)),
    )

    warnings = [
        _failure("warning", "low", str(value), target=str(value))
        for value in legacy.get("warnings") or []
    ]
    feedback = _feedback_lines(passed, checks, failures, warnings, language=language)

    return {
        "passed": passed,
        "is_acceptable": evaluation_result.is_acceptable,
        "score": score,
        "checks": checks,
        "failures": failures,
        "hard_failures": [failure.model_dump() for failure in evaluation_result.hard_failures],
        "soft_failures": [failure.model_dump() for failure in evaluation_result.soft_failures],
        "evaluation_result": evaluation_result.model_dump(),
        "warnings": warnings,
        "summary": _summary_lines(passed, checks, failures),
        "feedback": feedback,
        "natural_language_feedback": feedback,
        "legacy_validation": legacy,
    }


def public_evaluation(evaluation: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(evaluation, dict):
        return None
    return {
        "passed": bool(evaluation.get("passed")),
        "is_acceptable": bool(evaluation.get("is_acceptable", evaluation.get("passed"))),
        "score": evaluation.get("score"),
        "checks": dict(evaluation.get("checks") or {}),
        "failures": list(evaluation.get("failures") or []),
        "hard_failures": list(evaluation.get("hard_failures") or []),
        "soft_failures": list(evaluation.get("soft_failures") or []),
        "evaluation_result": dict(evaluation.get("evaluation_result") or {}),
        "warnings": list(evaluation.get("warnings") or []),
        "summary": list(evaluation.get("summary") or []),
        "feedback": list(evaluation.get("feedback") or evaluation.get("natural_language_feedback") or []),
        "natural_language_feedback": list(evaluation.get("natural_language_feedback") or evaluation.get("feedback") or []),
        "iterations": evaluation.get("iterations"),
        "improved": evaluation.get("improved"),
        "initial_score": evaluation.get("initial_score"),
    }


def evaluation_signature(evaluation: dict[str, Any] | None) -> tuple[str, ...]:
    if not isinstance(evaluation, dict):
        return ()
    values = [
        f"{failure.get('failure_type') or failure.get('type')}:{failure.get('target')}"
        for failure in evaluation.get("failures") or []
        if isinstance(failure, dict)
    ]
    values.extend(
        f"check:{key}:{value}"
        for key, value in sorted((evaluation.get("checks") or {}).items())
        if value != "passed"
    )
    return tuple(sorted(set(str(value) for value in values if str(value).strip())))


def should_replan(evaluation: dict[str, Any] | None) -> bool:
    if not isinstance(evaluation, dict):
        return False
    if not evaluation.get("passed"):
        return True
    try:
        return float(evaluation.get("score") or 0) < 0.82
    except (TypeError, ValueError):
        return False


def _failure(issue_type: str, severity: str, message: str, *, target: str | None = None) -> dict[str, Any]:
    failure_type, normalized_severity, repair_hint = _canonical_failure(issue_type, severity, target)
    failure = PlanFailure(
        failure_type=failure_type,
        severity=normalized_severity,
        target=target,
        reason=message,
        repair_hint=repair_hint,
    )
    data = failure.model_dump()
    data.update(
        {
            # Backward-compatible fields consumed by the current frontend and replanner.
            "type": issue_type,
            "legacy_severity": severity,
            "message": message,
        }
    )
    return data


def _canonical_failure(issue_type: str, severity: str, target: str | None) -> tuple[str, str, str | None]:
    if issue_type == "missing_required_anchor":
        return ft.MUST_INCLUDE_MISSING, "hard", "insert_place"
    if issue_type == "must_avoid_violation":
        return ft.MUST_AVOID_INCLUDED, "hard", "remove_place"
    if issue_type == "final_anchor_mismatch":
        return ft.FINAL_ANCHOR_VIOLATION, "hard", "move_place_to_final"
    if issue_type == "order_mismatch":
        return ft.ORDERED_ANCHOR_VIOLATION, "hard", "reorder_by_anchor_order"
    if issue_type == "duplicate_place":
        return ft.DUPLICATE_PLACE, "hard", "remove_duplicate_places"
    if issue_type == "duplicate_day_pattern":
        return ft.DUPLICATE_DAY_PATTERN, "hard", "regenerate_duplicate_days"
    if issue_type == "low_walking_violation":
        return ft.LOW_WALKING_VIOLATION, "hard", "reduce_walking_burden"
    if issue_type == "time_slot_mismatch":
        return ft.TIME_SLOT_MISMATCH, "soft", "move_place_to_time_slot"
    if issue_type == "pace_mismatch":
        if target and "slow" in target.lower():
            return ft.PACE_TOO_SLOW, "soft", "rebalance_pace"
        return ft.PACE_TOO_FAST, "soft", "reduce_place_count_for_slow_pace"
    if issue_type == "meal_preference_mismatch":
        return ft.MEAL_STYLE_MISMATCH, "soft", "improve_meal_style"
    if issue_type in {"helper_gap_quality", "story_flow_issue", "story_flow"}:
        return ft.STORY_FLOW_WEAK, "soft", "improve_story_flow"
    if issue_type == "museum_limit_violation":
        return ft.TRAVEL_STYLE_MISMATCH, "soft", "reduce_repetitive_category"
    if issue_type == "warning":
        return ft.STORY_FLOW_WEAK, "soft", None
    normalized = "hard" if severity == "high" else "soft"
    return issue_type.upper(), normalized, None


def _plan_failure_from_dict(failure: dict[str, Any]) -> PlanFailure:
    return PlanFailure(
        failure_type=str(failure.get("failure_type") or failure.get("type") or ""),
        severity="hard" if failure.get("severity") == "hard" else "soft",
        target=failure.get("target"),
        expected=failure.get("expected"),
        actual=failure.get("actual"),
        reason=str(failure.get("reason") or failure.get("message") or failure.get("failure_type") or failure.get("type") or ""),
        repair_hint=failure.get("repair_hint"),
    )


def _legacy_failure(issue_type: str, severity: str, message: str, *, target: str | None = None) -> dict[str, Any]:
    return {
        "type": issue_type,
        "severity": severity,
        "message": message,
        "target": target,
    }


def _meal_failure(value: str) -> dict[str, Any]:
    target = "meal_preference"
    issue_type = "meal_preference_mismatch"
    if "french" in value or "dinner" in value:
        target = "french_dinner"
        issue_type = "missing_required_anchor"
    elif "brunch" in value:
        target = "brunch"
        issue_type = "missing_required_anchor"
    elif "cafe" in value or "dessert" in value:
        target = "cafe"
        issue_type = "missing_required_anchor"
    elif "bar" in value or "jazz" in value:
        target = "jazz_bar"
        issue_type = "missing_required_anchor"
    return _failure(
        issue_type,
        "high",
        f"Requested meal preference is not represented: {value}",
        target=target,
    )


def _summary_lines(passed: bool, checks: dict[str, str], failures: list[dict[str, Any]]) -> list[str]:
    if passed:
        return [
            "Required anchors checked",
            "Avoid constraints checked",
            "Time and route quality checked",
            "Pace and duplicate places checked",
        ]
    high = [failure for failure in failures if failure.get("severity") == "hard" or failure.get("legacy_severity") == "high"]
    if high:
        return [str(failure.get("message") or failure.get("type")) for failure in high[:4]]
    return [f"{key}: {value}" for key, value in checks.items() if value != "passed"][:4]


def _feedback_lines(
    passed: bool,
    checks: dict[str, str],
    failures: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    *,
    language: str,
) -> list[str]:
    ko = str(language or "").lower().startswith("ko")
    if passed:
        return (
            [
                "요청 조건, 중복 장소, 시간대 의미, 동선 품질을 검토했고 통과했습니다.",
                "Replanner 수정 없이 MongoDB 저장이 가능한 일정입니다.",
            ]
            if ko
            else [
                "The itinerary passed request, duplicate, time-semantics, and route-quality checks.",
                "No replanning is required before saving to MongoDB.",
            ]
        )

    high_or_medium = [
        failure
        for failure in failures
        if str(failure.get("severity") or "") in {"hard", "soft"}
        or str(failure.get("legacy_severity") or "") in {"high", "medium"}
    ]
    messages = [_feedback_message(failure, ko=ko) for failure in high_or_medium[:5]]
    if not messages:
        messages = [
            (f"{key} 검토가 {value} 상태입니다." if ko else f"{key} check is {value}.")
            for key, value in checks.items()
            if value != "passed"
        ][:4]
    if warnings and len(messages) < 5:
        warning = warnings[0]
        messages.append(
            f"주의: {warning.get('message') or warning.get('target')}"
            if ko
            else f"Warning: {warning.get('message') or warning.get('target')}"
        )
    return messages


def _feedback_message(failure: dict[str, Any], *, ko: bool) -> str:
    issue_type = str(failure.get("type") or "")
    target = str(failure.get("target") or "").strip()
    if not ko:
        return str(failure.get("message") or issue_type)
    if issue_type == "missing_required_anchor":
        return f"사용자가 요청한 {target or '필수 요소'}가 일정에 빠졌습니다."
    if issue_type == "must_avoid_violation":
        return f"사용자가 제외한 {target or '장소'}가 일정에 포함되었습니다."
    if issue_type == "time_slot_mismatch":
        return f"{target or '요청 장소'}의 시간대가 사용자 의도와 맞지 않습니다."
    if issue_type == "final_anchor_mismatch":
        return f"마지막 장소 요청이 {target or '요청 anchor'}로 마무리되지 않았습니다."
    if issue_type == "duplicate_place":
        return f"{target or '장소'}가 일정 안에서 중복 배치되었습니다."
    if issue_type == "order_mismatch":
        return f"요청한 방문 순서가 일정에 제대로 반영되지 않았습니다: {target}"
    if issue_type == "pace_mismatch":
        return "일정 밀도가 사용자가 원하는 여행 속도와 맞지 않습니다."
    if issue_type == "helper_gap_quality":
        return "빈 시간/보조 블록이 많아 하루 흐름이 약합니다."
    if issue_type == "story_flow_issue":
        return "하루의 감정 흐름이나 장소 연결이 자연스럽지 않습니다."
    return str(failure.get("message") or issue_type)


def _dedupe_failures(failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for failure in failures:
        key = (str(failure.get("type") or ""), str(failure.get("target") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(failure)
    return deduped


def _raw_constraint_failures(
    itinerary_days: list[dict[str, Any]],
    brief: dict[str, Any],
    prompt: str,
) -> list[dict[str, Any]]:
    text = _dedupe_text_parts([prompt, brief.get("source_text")])
    compact = _normalize(text)
    failures: list[dict[str, Any]] = []
    structured_timed_targets = {
        str(constraint.get("canonical") or "").strip()
        for constraint in brief.get("place_constraints") or []
        if isinstance(constraint, dict)
        and str(constraint.get("intent") or "") != "avoid"
        and str(constraint.get("time_slot") or "").strip()
    }

    for target, aliases in FINAL_TARGET_ALIASES.items():
        if target == "marais":
            continue
        if _raw_avoid_target(compact, aliases) and _find_item(itinerary_days, target) is not None:
            failures.append(
                _failure(
                    "must_avoid_violation",
                    "high",
                    f"Raw request excludes this target, but it appears in the itinerary: {target}",
                    target=target,
                )
            )

    for target, aliases in FINAL_TARGET_ALIASES.items():
        if _raw_avoid_target(compact, aliases):
            continue
        if _raw_place_requested(compact, aliases) and _find_item(itinerary_days, target) is None:
            failures.append(
                _failure(
                    "missing_required_anchor",
                    "high",
                    f"Raw request mentions a required target that is missing: {target}",
                    target=target,
                )
            )
            continue
        requested_slot = None if target in structured_timed_targets else _raw_requested_slot(compact, aliases)
        if requested_slot:
            item = _find_item(itinerary_days, target)
            if item is None:
                failures.append(
                    _failure(
                        "missing_required_anchor",
                        "high",
                        f"Raw request mentions a timed target that is missing: {target}",
                        target=target,
                    )
                )
            elif not _slot_matches(item, requested_slot):
                failures.append(
                    _failure(
                        "time_slot_mismatch",
                        "high",
                        f"Raw request expects {target} in {requested_slot}, but itinerary places it elsewhere.",
                        target=target,
                )
            )

    if _raw_evening_only_requested(compact):
        first_minutes = _first_item_minutes(itinerary_days)
        if first_minutes is not None and first_minutes < 17 * 60:
            failures.append(
                _failure(
                    "time_slot_mismatch",
                    "high",
                    "Raw request says the itinerary is evening-only, but it starts before evening.",
                    target="evening_only_start",
                )
            )

    if _raw_late_start_requested(compact):
        first_minutes = _first_item_minutes(itinerary_days)
        if first_minutes is not None and first_minutes < 10 * 60:
            failures.append(
                _failure(
                    "time_slot_mismatch",
                    "high",
                    "Raw request asks for a later start, but the itinerary starts before 10:00.",
                    target="late_start",
                )
            )

    if _raw_early_finish_requested(compact):
        last_minutes = _last_item_minutes(itinerary_days)
        if last_minutes is not None and last_minutes >= 20 * 60 + 30:
            failures.append(
                _failure(
                    "time_slot_mismatch",
                    "high",
                    "Raw request asks to avoid a late night, but the itinerary ends too late.",
                    target="early_finish",
                )
            )

    if _raw_french_dinner_requested(compact) and not _has_evening_french_dinner(itinerary_days):
        failures.append(
            _failure(
                "missing_required_anchor",
                "high",
                "Raw request asks for a French dinner or bistro, but no evening French meal is scheduled.",
                target="french_dinner",
            )
        )

    if _raw_museum_limit_requested(compact) and _museum_count(itinerary_days) > 1:
        failures.append(
            _failure(
                "museum_limit_violation",
                "high",
                "Raw request asks for at most one museum, but multiple museum stops are scheduled.",
                target="museum_count_le1",
            )
        )

    return failures


def _structured_constraint_failures(
    itinerary_days: list[dict[str, Any]],
    brief: dict[str, Any],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for constraint in brief.get("place_constraints") or []:
        if not isinstance(constraint, dict):
            continue
        target = str(constraint.get("target") or constraint.get("canonical") or "").strip()
        intent = str(constraint.get("intent") or "").strip()
        target_slot = str(constraint.get("time_slot") or "").strip()
        if not target:
            continue
        item = _find_item(itinerary_days, target)
        if intent == "avoid":
            if item is not None:
                failures.append(
                    _failure(
                        "must_avoid_violation",
                        "high",
                        f"Structured constraint excludes this target, but it appears: {target}",
                        target=target,
                    )
                )
            continue
        if item is None:
            failures.append(
                _failure(
                    "missing_required_anchor",
                    "high",
                    f"Structured constraint requires this target, but it is missing: {target}",
                    target=target,
                )
            )
            continue
        if target_slot and not _slot_matches(item, target_slot):
            failures.append(
                _failure(
                    "time_slot_mismatch",
                    "high",
                    f"Structured constraint expects {target} in {target_slot}.",
                    target=target,
                )
            )
        if constraint.get("final") and not _final_item_matches(itinerary_days, target):
            failures.append(
                _failure(
                    "final_anchor_mismatch",
                    "high",
                    f"Structured constraint expects {target} as the final stop.",
                    target=target,
                )
            )

    ordered_anchors = [str(value) for value in brief.get("ordered_anchors") or [] if str(value).strip()]
    if len(ordered_anchors) >= 2:
        missing = [target for target in ordered_anchors if _find_item(itinerary_days, target) is None]
        for target in missing:
            failures.append(
                _failure(
                    "missing_required_anchor",
                    "high",
                    f"Ordered anchor is missing: {target}",
                    target=target,
                )
            )
        if not missing and not _ordered_anchors_match(itinerary_days, ordered_anchors):
            failures.append(
                _failure(
                    "order_mismatch",
                    "high",
                    "Ordered anchors do not follow the requested sequence.",
                    target=" > ".join(ordered_anchors),
                )
            )
    return failures


def _ordered_anchors_match(itinerary_days: list[dict[str, Any]], ordered_anchors: list[str]) -> bool:
    positions: list[int] = []
    items = _real_items(itinerary_days)
    for target in ordered_anchors:
        index = next((index for index, item in enumerate(items) if _matches_target(item, target)), None)
        if index is None:
            return False
        positions.append(index)
    return positions == sorted(positions)


def _raw_avoid_target(compact_text: str, aliases: tuple[str, ...]) -> bool:
    avoid_cues = (
        "\ub9d0\uace0",
        "\ub300\uc2e0",
        "\uc81c\uc678",
        "\ube7c",
        "\uc2eb",
        "\ubcf4\ub2e4",
        "skip",
        "exclude",
        "avoid",
        "instead",
    )
    include_after_cues = ("\uc0ac\uc9c4", "photo")
    for alias in aliases:
        alias_norm = _normalize(alias)
        if not alias_norm:
            continue
        alias_index = compact_text.find(alias_norm)
        if alias_index < 0:
            continue
        after = compact_text[alias_index + len(alias_norm) : alias_index + len(alias_norm) + 28]
        avoid_positions = [after.find(cue) for cue in avoid_cues if cue in after]
        if avoid_positions:
            avoid_index = min(avoid_positions)
            between = after[:avoid_index]
            next_alias_offset = _next_target_alias_offset(after)
            if 0 <= next_alias_offset < avoid_index and not any(token in between for token in ("\ub458\ub2e4", "\ubaa8\ub450", "\uc804\ubd80", "both", "all")):
                continue
            if _avoid_cue_belongs_to_other_subject(between):
                continue
            window = compact_text[alias_index : alias_index + len(alias_norm) + avoid_index + 8]
            if any(cue in window for cue in include_after_cues) and "\uc0ac\uc9c4\ub9cc" in window:
                return False
            return True
        before = compact_text[max(0, alias_index - 12) : alias_index]
        if any(cue in before for cue in ("skip", "exclude", "avoid")):
            return True
    return False


def _raw_place_requested(compact_text: str, aliases: tuple[str, ...]) -> bool:
    request_cues = (
        "\ub123\uc5b4",
        "\uc704\uc8fc",
        "\uc911\uc2ec",
        "\uc0b0\ucc45",
        "\ubcf4\uace0",
        "\uac00\uace0",
        "\uc774\uc5b4",
        "\ub9c8\ubb34\ub9ac",
        "\ub9c8\uc9c0\ub9c9",
        "\uaf2d",
        "\uc0ac\uc9c4",
        "include",
        "visit",
        "walk",
        "final",
    )
    for alias in aliases:
        alias_norm = _normalize(alias)
        if not alias_norm:
            continue
        alias_index = compact_text.find(alias_norm)
        if alias_index < 0:
            continue
        window = compact_text[max(0, alias_index - 12) : alias_index + len(alias_norm) + 22]
        if any(cue in window for cue in request_cues):
            return True
    return False


def _avoid_cue_belongs_to_other_subject(text_between_alias_and_cue: str) -> bool:
    return any(
        token in text_between_alias_and_cue
        for token in (
            "\ubc15\ubb3c\uad00",
            "\ubbf8\uc220\uad00",
            "\ubc24\uc77c\uc815",
            "\ubc24\ub2a6\uac8c",
            "\uc77c\uc815",
            "\uc7ac\uc988\ubc14",
        )
    )


def _next_target_alias_offset(text: str) -> int:
    offsets = [
        index
        for aliases in FINAL_TARGET_ALIASES.values()
        for alias in aliases
        if (normalized := _normalize(alias)) and (index := text.find(normalized)) >= 0
    ]
    return min(offsets) if offsets else -1


def _raw_requested_slot(compact_text: str, aliases: tuple[str, ...]) -> str | None:
    slot_cues = {
        "morning": ("\uc624\uc804", "\uc544\uce68", "\uc810\uc2ec\uc804", "morning"),
        "afternoon": ("\uc624\ud6c4", "afternoon"),
        "evening": ("\uc800\ub141", "\ubc24", "\uc57c\uacbd", "\uc11d\uc591", "\ub178\uc744", "evening", "night", "sunset"),
    }
    for alias in aliases:
        alias_norm = _normalize(alias)
        if not alias_norm:
            continue
        alias_index = compact_text.find(alias_norm)
        if alias_index < 0:
            continue
        before = compact_text[max(0, alias_index - 12) : alias_index]
        after = compact_text[alias_index + len(alias_norm) : alias_index + len(alias_norm) + 18]
        next_alias_offset = _next_target_alias_offset(after)
        if next_alias_offset >= 0:
            after = after[:next_alias_offset]
        for slot, cues in slot_cues.items():
            if any(_slot_cue_applies_before(before, cue) or _slot_cue_applies_after(after, cue) for cue in cues):
                return slot
    return None


def _slot_cue_applies_before(before_alias: str, cue: str) -> bool:
    cue_norm = _normalize(cue)
    if not cue_norm or cue_norm not in before_alias:
        return False
    distance = len(before_alias) - before_alias.rfind(cue_norm) - len(cue_norm)
    return distance <= 8


def _slot_cue_applies_after(after_alias: str, cue: str) -> bool:
    cue_norm = _normalize(cue)
    if not cue_norm or cue_norm not in after_alias:
        return False
    cue_index = after_alias.find(cue_norm)
    between = after_alias[:cue_index]
    if cue_index <= 6:
        return not _slot_cue_belongs_to_later_subject(between)
    return False


def _slot_cue_belongs_to_later_subject(text_between_alias_and_cue: str) -> bool:
    return any(
        token in text_between_alias_and_cue
        for token in (
            "\uce74\ud398",
            "\uc2dd\uc0ac",
            "\ub514\ub108",
            "\ud504\ub80c\uce58",
            "\ube44\uc2a4\ud2b8\ub85c",
            "\uc7ac\uc988",
            "\uc0b0\ucc45",
        )
    )


def _raw_evening_only_requested(compact_text: str) -> bool:
    return any(token in compact_text for token in ("\uc800\ub141\ub9cc", "\ubc24\ub9cc", "eveningonly", "onlyevening"))


def _raw_late_start_requested(compact_text: str) -> bool:
    return any(
        token in compact_text
        for token in (
            "\uc544\uce68\uc77c\ucc0d\ub9d0\uace0",
            "\uc77c\ucc0d\uc2dc\uc791\ub9d0\uace0",
            "\uc77c\ucc0d\uc2dc\uc791\ud558\uc9c0\ub9d0\uace0",
            "\uc544\uce68\ub2a6\uac8c",
            "\ub2a6\uac8c\uc2dc\uc791",
            "\uc624\uc804\uc740\ube44\uc6cc",
            "11\uc2dc\uc774\ud6c4",
            "late",
            "startlate",
        )
    )


def _raw_early_finish_requested(compact_text: str) -> bool:
    return any(
        token in compact_text
        for token in (
            "\ub108\ubb34\ub2a6\uc9c0",
            "\ub2a6\uc9c0\uc54a\uac8c",
            "\ub2a6\uc9c0",
            "\uc77c\ucc0d\ub05d",
            "\uc800\ub141\uc804",
            "\ubc24\uc77c\uc815\uc740\ube7c",
            "\ubc24\ub2a6\uac8c\uae4c\uc9c0\ub9d0\uace0",
            "nottoolate",
            "earlyfinish",
        )
    )


def _raw_french_dinner_requested(compact_text: str) -> bool:
    has_french = any(token in compact_text for token in ("french", "bistro", "\ud504\ub80c\uce58", "\ube44\uc2a4\ud2b8\ub85c"))
    has_dinner = any(token in compact_text for token in ("dinner", "evening", "\uc800\ub141", "\ub9c8\uc9c0\ub9c9"))
    return has_french and has_dinner


def _raw_museum_limit_requested(compact_text: str) -> bool:
    has_museum = any(token in compact_text for token in ("\ubbf8\uc220\uad00", "\ubc15\ubb3c\uad00", "museum", "gallery"))
    has_limit = any(token in compact_text for token in ("\ud558\ub098", "\ud558\ub098\ub9cc", "\ud55c\uacf3", "1\uacf3", "\ucd5c\uc18c", "one", "single"))
    return has_museum and has_limit


def _museum_count(itinerary_days: list[dict[str, Any]]) -> int:
    return sum(1 for item in _real_items(itinerary_days) if _is_museum_item(item))


def _is_museum_item(item: dict[str, Any]) -> bool:
    place = item.get("place") or {}
    category = str(place.get("category") or "").lower()
    text = _item_text(item)
    return category in {"museum", "gallery"} or any(token in text for token in ("louvre", "orsay", "\ub8e8\ube0c\ub974", "\uc624\ub974\uc138"))


def _has_evening_french_dinner(itinerary_days: list[dict[str, Any]]) -> bool:
    for item in _real_items(itinerary_days):
        if not _slot_matches(item, "evening"):
            continue
        place = item.get("place") or {}
        category = str(place.get("category") or "").lower()
        text = _item_text(item)
        if category in {"restaurant", "bistro", "brasserie"} and any(
            token in text for token in ("french", "bistro", "brasserie", "\ud504\ub80c\uce58", "\ube44\uc2a4\ud2b8\ub85c")
        ):
            return True
    return False


def _first_item_minutes(itinerary_days: list[dict[str, Any]]) -> int | None:
    items = _real_items(itinerary_days)
    return _item_minutes(items[0]) if items else None


def _last_item_minutes(itinerary_days: list[dict[str, Any]]) -> int | None:
    items = _real_items(itinerary_days)
    return _item_minutes(items[-1]) if items else None


def _adjusted_score(base_score: float, failures: list[dict[str, Any]], checks: dict[str, str]) -> float:
    penalty = 0.0
    for failure in failures:
        severity = failure.get("severity")
        legacy_severity = failure.get("legacy_severity")
        if severity == "hard" or legacy_severity == "high":
            penalty += 0.10
        elif severity == "soft" or legacy_severity == "medium":
            penalty += 0.05
        else:
            penalty += 0.02
    penalty += sum(0.03 for value in checks.values() if value == "warning")
    return round(max(0.0, min(1.0, base_score - penalty)), 2)


def _float_score(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _route_status(legacy: dict[str, Any]) -> str:
    route_score = _float_score(legacy.get("route_score"), default=1.0)
    if route_score < 0.76:
        return "failed"
    if route_score < 0.9:
        return "warning"
    return "passed"


def _locked_stop_failures(itinerary_days: list[dict[str, Any]], brief: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for lock in brief.get("locked_stops") or []:
        if not isinstance(lock, dict):
            continue
        target = str(lock.get("slug") or lock.get("place_id") or lock.get("label") or "").strip()
        target_slot = str(lock.get("target_slot") or "").strip()
        if not target or not target_slot:
            continue
        structured_slot = _structured_slot_for_target(brief, target)
        if structured_slot:
            target_slot = structured_slot
        item = _find_item(itinerary_days, target)
        if item is None:
            failures.append(
                _failure(
                    "missing_required_anchor",
                    "high",
                    f"Locked stop is missing: {target}",
                    target=target,
                )
            )
            continue
        if not _slot_matches(item, target_slot):
            failures.append(
                _failure(
                    "time_slot_mismatch",
                    "high",
                    f"Locked stop is not in the requested slot: {target} -> {target_slot}",
                    target=target,
                )
            )
    return failures


def _structured_slot_for_target(brief: dict[str, Any], target: str) -> str | None:
    target_norm = _normalize(target)
    target_canonical = _canonical_from_text(target)
    for constraint in brief.get("place_constraints") or []:
        if not isinstance(constraint, dict) or str(constraint.get("intent") or "") == "avoid":
            continue
        slot = str(constraint.get("time_slot") or "").strip()
        if not slot:
            continue
        constraint_target = str(constraint.get("target") or "")
        constraint_norm = _normalize(constraint_target)
        constraint_canonical = str(constraint.get("canonical") or "").strip()
        if (
            (target_norm and constraint_norm and (target_norm in constraint_norm or constraint_norm in target_norm))
            or (target_canonical and constraint_canonical == target_canonical)
        ):
            return slot
    return None


def _canonical_from_text(text: str) -> str | None:
    compact = _normalize(text)
    if not compact:
        return None
    for canonical, aliases in FINAL_TARGET_ALIASES.items():
        if any((alias_norm := _normalize(alias)) and alias_norm in compact for alias in aliases):
            return canonical
    return None


def _slot_matches(item: dict[str, Any], target_slot: str) -> bool:
    slot = str(item.get("time_slot") or "")
    minutes = _item_minutes(item)
    if target_slot == "morning":
        return slot == "morning" or (minutes is not None and minutes < 12 * 60)
    if target_slot == "afternoon":
        return slot == "afternoon" or (minutes is not None and 13 * 60 <= minutes < 18 * 60)
    if target_slot in {"evening", "night"}:
        return slot in {"evening", "night"} or (minutes is not None and minutes >= 18 * 60)
    return slot == target_slot


def _duplicate_place_targets(itinerary_days: list[dict[str, Any]]) -> list[str]:
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for item in _real_items(itinerary_days):
        key = _item_key(item)
        if not key:
            continue
        label = str((item.get("place") or {}).get("name") or item.get("title") or key)
        if key in seen and label not in duplicates:
            duplicates.append(label)
        else:
            seen[key] = label
    return duplicates


def _duplicate_day_pattern_targets(itinerary_days: list[dict[str, Any]]) -> list[str]:
    seen: dict[tuple[str, ...], int] = {}
    duplicates: list[str] = []
    for fallback_index, day in enumerate(itinerary_days or [], start=1):
        try:
            day_number = int(day.get("day_number") or fallback_index)
        except (TypeError, ValueError):
            day_number = fallback_index
        keys = tuple(
            key
            for item in _real_items([day])
            if (key := _item_key(item))
        )
        if len(keys) < 3:
            continue
        if keys in seen:
            duplicates.append(f"day_{seen[keys]}_and_day_{day_number}")
            continue
        seen[keys] = day_number
    return duplicates


def _low_walking_failures(
    itinerary_days: list[dict[str, Any]],
    brief: dict[str, Any],
    prompt: str,
) -> list[str]:
    if not _low_walking_requested(brief, prompt):
        return []
    failures: list[str] = []
    for day in itinerary_days or []:
        day_number = day.get("day_number") or "?"
        for item in day.get("items") or []:
            if item.get("itemKind") == "gap":
                continue
            duration = _item_duration_minutes(item)
            if duration >= 75 and _is_walk_like_item(item):
                label = str((item.get("place") or {}).get("name") or item.get("title") or "walk")
                failures.append(f"day_{day_number}_{label}_{duration}min")
            route = item.get("route_to_next")
            if not isinstance(route, dict):
                continue
            mode = str(route.get("mode") or "").lower()
            minutes = int(route.get("totalTransferMinutes") or route.get("rawDurationMinutes") or 0)
            distance = int(route.get("distance_meters") or 0)
            if mode == "walk" and (minutes >= 25 or distance >= 1800):
                label = str((item.get("place") or {}).get("name") or item.get("title") or "route")
                failures.append(f"day_{day_number}_after_{label}_{minutes}min_walk")
    return failures


def _low_walking_requested(brief: dict[str, Any], prompt: str = "") -> bool:
    mobility = brief.get("mobility_constraints") if isinstance(brief.get("mobility_constraints"), dict) else {}
    if str(brief.get("walking_intensity") or mobility.get("walking_intensity") or "").lower() == "low":
        return True
    if bool(mobility.get("prefer_transit_between_areas")):
        return True
    compact = _normalize(
        " ".join(
            [
                prompt,
                str(brief.get("source_text") or ""),
                " ".join(str(value) for value in brief.get("must_avoid") or []),
                " ".join(str(value) for value in brief.get("travel_style") or []),
            ]
        )
    )
    return any(
        token in compact
        for token in (
            "lesswalking",
            "lowwalking",
            "avoidwalking",
            "notmuchwalking",
            "nolongwalks",
            "\ub9ce\uc774\uac77\uae30\uc2eb",
            "\ub9ce\uc774\uc548\uac77",
            "\ub3c4\ubcf4\ubd80\ub2f4",
            "\uac77\ub294\uac70\uc2eb",
            "\uc774\ub3d9\uac15\ub3c4\ub0ae",
        )
    )


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
            "\uc138\ub098",
            "\uc13c\uac15",
        )
    )


def _item_duration_minutes(item: dict[str, Any]) -> int:
    try:
        return int(item.get("duration_minutes") or 0)
    except (TypeError, ValueError):
        return 0


def _final_item_matches(itinerary_days: list[dict[str, Any]], target: str) -> bool:
    items = _real_items(itinerary_days)
    if not items:
        return False
    return _matches_target(items[-1], target)


def _requested_final_target(brief: dict[str, Any], prompt: str) -> str | None:
    text = _dedupe_text_parts(
        [
            prompt,
            brief.get("source_text"),
        ]
    )
    compact = _normalize(text)
    cue_positions = [compact.find(_normalize(cue)) for cue in FINAL_CUES if _normalize(cue) in compact]
    cue_positions = [position for position in cue_positions if position >= 0]
    if not cue_positions:
        return None
    candidates: list[tuple[int, int, str]] = []
    for cue_position in cue_positions:
        for target, aliases in FINAL_TARGET_ALIASES.items():
            if _raw_avoid_target(compact, aliases):
                continue
            for alias in aliases:
                alias_norm = _normalize(alias)
                if not alias_norm:
                    continue
                alias_index = compact.find(alias_norm)
                if alias_index < 0:
                    continue
                distance = alias_index - cue_position
                if 0 <= distance <= 42:
                    candidates.append((0, distance, target))
                elif -32 <= distance < 0:
                    candidates.append((1, abs(distance), target))
    if candidates:
        return sorted(candidates)[0][2]
    for target, aliases in FINAL_TARGET_ALIASES.items():
        if _raw_avoid_target(compact, aliases):
            continue
        if _final_cue_near_alias(compact, aliases):
            return target
    return None


def _final_cue_near_alias(compact_text: str, aliases: tuple[str, ...]) -> bool:
    cue_positions = [compact_text.find(_normalize(cue)) for cue in FINAL_CUES if _normalize(cue) in compact_text]
    if not cue_positions:
        return False
    for alias in aliases:
        normalized_alias = _normalize(alias)
        if not normalized_alias:
            continue
        alias_index = compact_text.find(normalized_alias)
        if alias_index < 0:
            continue
        if any(abs(alias_index - cue_index) <= 40 for cue_index in cue_positions):
            return True
    return False


def _find_item(itinerary_days: list[dict[str, Any]], target: str) -> dict[str, Any] | None:
    for item in _real_items(itinerary_days):
        if _matches_target(item, target):
            return item
    return None


def _matches_target(item: dict[str, Any], target: str) -> bool:
    text = _item_text(item)
    target_norms = _target_norms(target)
    return any(norm and (norm in text or text in norm) for norm in target_norms)


def _target_norms(target: str) -> set[str]:
    normalized = _normalize(target)
    norms = {normalized} if normalized else set()
    for aliases in FINAL_TARGET_ALIASES.values():
        alias_norms = {_normalize(alias) for alias in aliases}
        if normalized in alias_norms or any(alias and alias in normalized for alias in alias_norms):
            norms.update(alias_norms)
    return norms


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


def _dedupe_text_parts(values: list[Any]) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = _normalize(text)
        if key in seen:
            continue
        seen.add(key)
        parts.append(text)
    return " ".join(parts)


def _item_minutes(item: dict[str, Any]) -> int | None:
    raw = str(item.get("start_time") or "")
    if ":" not in raw:
        return None
    try:
        hour, minute = raw.split(":", 1)
        return int(hour) * 60 + int(minute)
    except ValueError:
        return None


def _real_items(itinerary_days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for day in itinerary_days or []
        for item in day.get("items") or []
        if item.get("itemKind") != "gap"
    ]


def _normalize(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).lower()
    return re.sub(r"[^0-9a-zA-Z\uac00-\ud7a3]+", "", normalized)
