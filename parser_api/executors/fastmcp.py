from __future__ import annotations

import asyncio
import warnings
from typing import Any

warnings.filterwarnings(
    "ignore",
    message="authlib.jose module is deprecated, please use joserfc instead.*",
)

from fastmcp import Client

from parser_api.executors.base import ExecutionRequest, ExecutionResult
from parser_api.intents import Intent
from parser_api.mcp_servers.registry import McpServiceRegistry, mcp_service_registry


class FastMcpExecutor:
    def __init__(
        self,
        *,
        intent: Intent,
        service_name: str,
        tool_name: str,
        registry: McpServiceRegistry | None = None,
    ) -> None:
        self.intent = intent
        self.service_name = service_name
        self.tool_name = tool_name
        self._registry = registry or mcp_service_registry

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        server = self._registry.get(self.service_name)
        result = asyncio.run(
            self._call_tool(
                server=server,
                payload=request.parsed_payload.model_dump(),
                context=request.context,
            )
        )
        data = dict(result.get("data") or {})
        trip_id = str(result.get("trip_id") or "")
        return ExecutionResult(trip_id=trip_id, data=data)

    async def _call_tool(
        self,
        *,
        server: Any,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        async with Client(server) as client:
            result = await client.call_tool(
                self.tool_name,
                {
                    "payload": payload,
                    "context": context,
                },
            )
        return dict(result.data or {})
