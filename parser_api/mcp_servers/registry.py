from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from parser_api.mcp_servers.discovery_server import mcp as discovery_server
from parser_api.mcp_servers.place_catalog_server import mcp as place_catalog_server
from parser_api.mcp_servers.planning_server import mcp as planning_server
from parser_api.mcp_servers.profile_server import mcp as profile_server


@dataclass(slots=True)
class McpServiceRegistry:
    services: dict[str, Any]

    def get(self, name: str) -> Any:
        return self.services[name]


def build_default_mcp_service_registry() -> McpServiceRegistry:
    return McpServiceRegistry(
        services={
            "planning": planning_server,
            "discovery": discovery_server,
            "profile": profile_server,
            "catalog": place_catalog_server,
        }
    )


mcp_service_registry = build_default_mcp_service_registry()
