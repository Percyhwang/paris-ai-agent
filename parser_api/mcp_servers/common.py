from __future__ import annotations

import warnings
from typing import Any

warnings.filterwarnings(
    "ignore",
    message="authlib.jose module is deprecated, please use joserfc instead.*",
)

try:
    from fastmcp import FastMCP
except ModuleNotFoundError:
    class FastMCP:  # type: ignore[override]
        def __init__(self, name: str) -> None:
            self.name = name

        def tool(self, fn):
            return fn

        def run(self) -> None:
            raise RuntimeError("fastmcp is not installed in this environment.")

from parser_api.intents import Intent


def build_server(name: str) -> FastMCP:
    return FastMCP(name)


def build_meta(service: str, tool: str) -> dict[str, str]:
    return {
        "mcp": "fastmcp",
        "server": service,
        "tool": tool,
    }


def strip_clarify(payload_dict: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload_dict)
    normalized.pop("clarify", None)
    return normalized


def build_tool_response(
    *,
    intent: Intent,
    data_key: str,
    payload_dict: dict[str, Any],
    service: str,
    tool: str,
    trip_id: str = "",
    payload_extras: dict[str, Any] | None = None,
    top_level_extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_payload = strip_clarify(payload_dict)
    if payload_extras:
        normalized_payload.update(payload_extras)

    data = {
        "intent": intent.value,
        data_key: normalized_payload,
        "meta": build_meta(service, tool),
    }
    if top_level_extras:
        data.update(top_level_extras)

    return {
        "trip_id": trip_id,
        "data": data,
    }
