from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from parser_api.intents import Intent
from parser_api.parsers.base import ParsedPayload


@dataclass(slots=True)
class ExecutionRequest:
    intent: Intent
    message: str
    context: dict[str, Any]
    parsed_payload: ParsedPayload
    data_key: str


@dataclass(slots=True)
class ExecutionResult:
    trip_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class BaseExecutor(Protocol):
    intent: Intent

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        ...
