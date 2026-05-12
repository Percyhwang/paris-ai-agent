from typing import Optional

from pydantic import ValidationError

from parser_api.intents import Intent
from parser_api.parsers.create_plan.normalize import _normalize_llm_payload
from parser_api.parsers.create_plan.rules import _apply_rule_overrides
from parser_api.parsers.llm import LLMStructuredOutputError, _call_llm_structured
from parser_api.schemas import CreatePlanPayload


class CreatePlanParser:
    intent = Intent.CREATE_PLAN

    def parse(self, message: str, context: Optional[dict] = None) -> CreatePlanPayload:
        del context
        last_error: Optional[Exception] = None

        for attempt in range(2):
            try:
                raw = _call_llm_structured(message)
                raw = _normalize_llm_payload(raw)
                plan = CreatePlanPayload.model_validate(raw)
                plan = _apply_rule_overrides(plan, message)
                return plan
            except (ValidationError, LLMStructuredOutputError) as exc:
                last_error = exc
                print(f"[CREATE_PLAN_PARSER] attempt {attempt + 1} failed: {repr(exc)}")
            except Exception as exc:
                print(f"[CREATE_PLAN_PARSER] unexpected error: {repr(exc)}")
                raise

        print(f"[CREATE_PLAN_PARSER] fallback to rules. last_error={repr(last_error)}")
        plan = CreatePlanPayload()
        plan = _apply_rule_overrides(plan, message)
        return plan


CREATE_PLAN_PARSER = CreatePlanParser()


def parse_create_plan(message: str, context: Optional[dict] = None) -> CreatePlanPayload:
    return CREATE_PLAN_PARSER.parse(message, context)
