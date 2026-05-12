from __future__ import annotations

from typing import Any

from parser_api.executors.base import ExecutionRequest, ExecutionResult
from parser_api.intents import Intent
from parser_api.mcp_servers import (
    discovery_server as discovery_module,
    place_catalog_server as place_catalog_module,
    planning_server as planning_module,
    profile_server as profile_module,
)

SERVICE_MODULES: dict[str, Any] = {
    "planning": planning_module,
    "discovery": discovery_module,
    "profile": profile_module,
    "catalog": place_catalog_module,
}


class LocalMcpExecutor:
    def __init__(
        self,
        *,
        intent: Intent,
        service_name: str,
        tool_name: str,
    ) -> None:
        self.intent = intent
        self.service_name = service_name
        self.tool_name = tool_name

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        module = SERVICE_MODULES[self.service_name]
        handler = getattr(module, self.tool_name)
        result = handler(
            request.parsed_payload.model_dump(),
            request.context,
        )
        return ExecutionResult(
            trip_id=str(result.get("trip_id") or ""),
            data=dict(result.get("data") or {}),
        )
