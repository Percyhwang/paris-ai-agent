from __future__ import annotations

from typing import Any

from parser_api.intents import Intent
from parser_api.mcp_servers.common import build_server, build_tool_response
from parser_api.schemas import TravelStylePayload, UserProfilePayload
from parser_api.services.profile_store import get_user_profile, update_user_profile

SERVICE_NAME = "profile-service"
mcp = build_server(SERVICE_NAME)


def _build_style_summary(payload: TravelStylePayload) -> str:
    tags = ", ".join(payload.style_tags) if payload.style_tags else "general"
    focus = ", ".join(payload.venue_focus) if payload.venue_focus else "balanced"
    return f"스타일 태그는 {tags}, 주요 포커스는 {focus}입니다."


@mcp.tool
def user_profile(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    validated = UserProfilePayload.model_validate(payload)
    stored_profile = get_user_profile()

    if validated.operation == "update":
        stored_profile = update_user_profile(validated.profile.model_dump())

    return build_tool_response(
        intent=Intent.USER_PROFILE,
        data_key="user_profile",
        payload_dict=validated.model_dump(),
        service=SERVICE_NAME,
        tool="user_profile",
        payload_extras={"stored_profile": stored_profile},
    )


@mcp.tool
def travel_style(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    validated = TravelStylePayload.model_validate(payload)
    return build_tool_response(
        intent=Intent.TRAVEL_STYLE,
        data_key="travel_style",
        payload_dict=validated.model_dump(),
        service=SERVICE_NAME,
        tool="travel_style",
        payload_extras={"style_summary": _build_style_summary(validated)},
    )


if __name__ == "__main__":
    mcp.run()
