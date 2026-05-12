import re
from typing import Optional

from parser_api.intents import Intent
from parser_api.parsers.common.constants import FAST_PACE_TOKENS, SLOW_PACE_TOKENS
from parser_api.parsers.common.extractors import extract_slots_in_order
from parser_api.parsers.modify_plan.inference import (
    _extract_target_day,
    _infer_category,
    _infer_op,
    _infer_place_name,
    _infer_quantity,
    _infer_quantity_change,
    _infer_replace_targets,
    _infer_target_slot,
)
from parser_api.parsers.modify_plan.patches import (
    _extract_constraint_patch,
    _extract_mobility_patch,
)
from parser_api.schemas import ModifyPlanPayload, Operation


def _build_operation(message: str) -> Operation:
    text = message.replace(" ", "")

    op = _infer_op(text)
    day = _extract_target_day(text)
    category = _infer_category(text)
    quantity = _infer_quantity(text)
    from_quantity, to_quantity = _infer_quantity_change(text)
    target_slot = _infer_target_slot(text)
    ordered_slots = extract_slots_in_order(text)
    swap_slots: Optional[list[str]] = None
    place_name = _infer_place_name(message, op)

    constraints_patch = None
    if op in {"set_quantity", "replace"}:
        quantity = None

    if op == "set_constraint":
        constraints_patch = _extract_constraint_patch(text)

    if ("미술관하루" in text or "박물관하루" in text) and "개만" in text:
        if constraints_patch is None:
            constraints_patch = {}
        match = re.search(r"(?:미술관|박물관)하루\s*(\d+)\s*개만", text)
        if match:
            constraints_patch["museum_per_day"] = int(match.group(1))
        elif quantity is not None:
            constraints_patch["museum_per_day"] = quantity
        else:
            constraints_patch["museum_per_day"] = 1
        op = "set_constraint"

    if op == "replace":
        replace_patch = _infer_replace_targets(message, category)
        if replace_patch:
            constraints_patch = {**(constraints_patch or {}), **replace_patch}

    if op == "swap":
        slots = list(ordered_slots)
        if len(slots) >= 2:
            swap_slots = slots[:2]
        target_slot = None

    mobility = _extract_mobility_patch(text)
    if mobility is not None and op not in {"swap", "move", "set_quantity", "set_constraint"}:
        op = "set_mobility"

    if op == "move" and len(ordered_slots) >= 2:
        constraints_patch = {
            **(constraints_patch or {}),
            "from_slot": ordered_slots[0],
            "to_slot": ordered_slots[1],
        }
        target_slot = ordered_slots[1]

    pace = None
    if op not in {"set_quantity", "set_constraint", "set_mobility"}:
        if any(token in text for token in SLOW_PACE_TOKENS) or any(
            token in text
            for token in (
                "줄여",
                "완화",
                "힘들",
                "부담",
                "너무많",
                "과해",
                "너무빡세",
                "빡세서",
                "너무타이트",
                "타이트해서",
            )
        ):
            pace = "slow"
            op = "set_pace"
        elif any(token in text for token in FAST_PACE_TOKENS) or (
            "타이트" in text and not any(token in text for token in ("너무타이트", "타이트해서"))
        ):
            pace = "fast"
            op = "set_pace"

    return Operation(
        op=op,
        target_day=day,
        target_slot=target_slot,
        swap_slots=swap_slots,
        category=category,
        place_name=place_name,
        quantity=quantity,
        from_quantity=from_quantity if op == "set_quantity" else None,
        to_quantity=to_quantity if op == "set_quantity" else None,
        constraints_patch=constraints_patch,
        pace=pace,
        mobility=mobility,
    )


def _apply_rule_overrides(
    payload: ModifyPlanPayload,
    message: str,
    context: Optional[dict[str, str]] = None,
) -> ModifyPlanPayload:
    payload.intent = Intent.MODIFY_PLAN.value

    if (not payload.trip_id) and context and isinstance(context.get("trip_id"), str):
        payload.trip_id = context["trip_id"]

    inferred = _build_operation(message)

    if not payload.operations:
        payload.operations = [inferred]
    else:
        for operation in payload.operations:
            if operation.target_day is None:
                operation.target_day = inferred.target_day
            if operation.target_slot is None and operation.op != "swap":
                operation.target_slot = inferred.target_slot
            if operation.swap_slots is None and operation.op == "swap":
                operation.swap_slots = inferred.swap_slots
            if operation.category is None:
                operation.category = inferred.category
            if operation.place_name is None:
                operation.place_name = inferred.place_name
            if operation.quantity is None:
                operation.quantity = inferred.quantity
            if operation.from_quantity is None:
                operation.from_quantity = inferred.from_quantity
            if operation.to_quantity is None:
                operation.to_quantity = inferred.to_quantity
            if operation.constraints_patch is None:
                operation.constraints_patch = inferred.constraints_patch
            if operation.pace is None:
                operation.pace = inferred.pace
            if operation.mobility is None:
                operation.mobility = inferred.mobility

    missing_fields: list[str] = []

    if not payload.trip_id:
        missing_fields.append("trip_id")
    elif not payload.operations:
        missing_fields.append("operations")
    else:

        def _needs_target_day(operation: Operation) -> bool:
            if operation.op in {"add", "swap", "move"}:
                return operation.target_day is None
            if operation.op == "set_quantity":
                return (
                    operation.target_day is None
                    and not operation.category
                    and not operation.place_name
                )
            if operation.op in {"remove", "replace"}:
                return operation.target_day is None and not operation.place_name
            return False

        if any(_needs_target_day(operation) for operation in payload.operations):
            missing_fields.append("operations.target_day")

    payload.clarify.missing_fields = list(dict.fromkeys(missing_fields))
    payload.clarify.needed = len(payload.clarify.missing_fields) > 0
    return payload

