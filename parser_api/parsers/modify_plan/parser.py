from typing import Optional

from pydantic import ValidationError

from parser_api.intents import Intent
from parser_api.parsers.llm import LLMStructuredOutputError, _call_llm_structured
from parser_api.parsers.modify_plan.normalize import _normalize_modify_payload
from parser_api.parsers.modify_plan.rules import _apply_rule_overrides
from parser_api.schemas import ModifyPlanPayload


class ModifyPlanParser:
    intent = Intent.MODIFY_PLAN

    def parse(self, message: str, context: Optional[dict] = None) -> ModifyPlanPayload:
        last_error: Optional[Exception] = None

        for attempt in range(2):
            try:
                raw = _call_llm_structured(message)
                raw = _normalize_modify_payload(raw)
                payload = ModifyPlanPayload.model_validate(raw)
                payload = _apply_rule_overrides(payload, message, context)
                return payload
            except (ValidationError, LLMStructuredOutputError) as exc:
                last_error = exc
                print(f"[MODIFY_PLAN_PARSER] attempt {attempt + 1} failed: {repr(exc)}")
            except Exception as exc:
                print(f"[MODIFY_PLAN_PARSER] unexpected error: {repr(exc)}")
                raise

        print(f"[MODIFY_PLAN_PARSER] fallback to rules. last_error={repr(last_error)}")
        payload = ModifyPlanPayload()
        payload = _apply_rule_overrides(payload, message, context)
        return payload


MODIFY_PLAN_PARSER = ModifyPlanParser()


def parse_modify_plan(message: str, context: Optional[dict] = None) -> ModifyPlanPayload:
    return MODIFY_PLAN_PARSER.parse(message, context)
