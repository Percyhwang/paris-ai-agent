import json
import os
from pathlib import Path
from typing import Any, Dict, TypeVar

from pydantic import BaseModel, ValidationError


class LLMStructuredOutputError(Exception):
    """Raised when LLM structured output cannot be parsed or validated."""


PayloadModel = TypeVar("PayloadModel", bound=BaseModel)


def _env_file_value(path: Path, key: str) -> str | None:
    if not path.exists():
        return None
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            env_key, raw_value = stripped.split("=", 1)
            if env_key.strip() == key:
                return raw_value.strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def _resolve_openai_api_key() -> str:
    if "OPENAI_API_KEY" in os.environ:
        api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if api_key and api_key != "sk-..." and not api_key.endswith("..."):
            return api_key
        raise LLMStructuredOutputError("OPENAI_API_KEY is not set in environment.")

    current_file = Path(__file__).resolve()
    for env_path in (
        current_file.parents[1] / ".env",
        current_file.parents[2] / ".env",
    ):
        api_key = (_env_file_value(env_path, "OPENAI_API_KEY") or "").strip()
        if api_key and api_key != "sk-..." and not api_key.endswith("..."):
            return api_key

    raise LLMStructuredOutputError("OPENAI_API_KEY is not set in environment.")


def _get_openai_client() -> Any:
    try:
        from openai import OpenAI
    except ModuleNotFoundError as exc:
        raise LLMStructuredOutputError("openai package is not installed.") from exc

    return OpenAI(api_key=_resolve_openai_api_key())


def _call_llm_structured(message: str, system_prompt: str | None = None) -> Dict[str, Any]:
    client = _get_openai_client()
    model = os.getenv("OPENAI_RESPONSE_MODEL", "gpt-4o-mini")
    prompt = system_prompt or (
        "You are a travel plan parser. Output ONLY a JSON object (no prose). "
        "If unknown, use null/empty objects."
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": prompt,
                },
                {"role": "user", "content": message},
            ],
            response_format={"type": "json_object"},
            max_tokens=1200,
        )
    except Exception as exc:
        raise LLMStructuredOutputError(f"OpenAI request failed: {exc}") from exc

    content = resp.choices[0].message.content
    if not isinstance(content, str):
        raise LLMStructuredOutputError("LLM response content is not a string JSON.")

    try:
        data = json.loads(content)
    except Exception as exc:
        raise LLMStructuredOutputError("Failed to json.loads() LLM output.") from exc

    if not isinstance(data, dict):
        raise LLMStructuredOutputError("LLM output is not a JSON object.")
    return data


def _is_meaningful(value: Any) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, list | tuple | set):
        return bool(value)
    if isinstance(value, dict):
        return any(_is_meaningful(child) for child in value.values())
    return True


def _merge_non_empty(base: Any, incoming: Any, defaults: Any) -> Any:
    if isinstance(base, dict) and isinstance(incoming, dict):
        merged = dict(base)
        default_dict = defaults if isinstance(defaults, dict) else {}
        for key, value in incoming.items():
            if not _is_meaningful(value):
                continue
            base_value = merged.get(key)
            default_value = default_dict.get(key)
            if isinstance(base_value, dict) and isinstance(value, dict):
                merged[key] = _merge_non_empty(base_value, value, default_value)
                continue
            if base_value != default_value and value == default_value:
                continue
            merged[key] = value
        return merged
    return incoming if _is_meaningful(incoming) else base


def _unwrap_payload(raw: dict[str, Any]) -> dict[str, Any]:
    for key in ("payload", "data", "result"):
        value = raw.get(key)
        if isinstance(value, dict):
            return value
    return raw


def augment_payload_with_llm(
    payload: PayloadModel,
    message: str,
    context: dict | None = None,
) -> PayloadModel:
    intent = str(getattr(payload, "intent", payload.__class__.__name__))
    model_cls = payload.__class__
    base_payload = payload.model_dump(mode="json")
    schema = model_cls.model_json_schema()
    prompt_payload = {
        "intent": intent,
        "message": message,
        "context": context or {},
        "current_rule_payload": base_payload,
        "json_schema": schema,
        "instructions": [
            "Return one JSON object matching json_schema.",
            "Use current_rule_payload as the baseline.",
            "Fill or correct fields when the user message clearly says so.",
            "Do not invent IDs, booking references, offer references, or trip IDs.",
            "Leave unknown fields null, empty, or omitted.",
            "Set clarify.needed and clarify.missing_fields only when required fields are missing.",
        ],
    }
    system_prompt = (
        "You are a deterministic travel intent parser. Output ONLY one JSON object "
        "that matches the requested schema. No markdown, no prose."
    )

    try:
        raw = _call_llm_structured(
            json.dumps(prompt_payload, ensure_ascii=False, default=str),
            system_prompt=system_prompt,
        )
        raw_payload = _unwrap_payload(raw)
        raw_payload["intent"] = intent
        default_payload = model_cls().model_dump(mode="json")
        merged = _merge_non_empty(base_payload, raw_payload, default_payload)
        return model_cls.model_validate(merged)
    except (LLMStructuredOutputError, ValidationError) as exc:
        print(f"[{intent}_PARSER] LLM augment skipped: {repr(exc)}")
        return payload
