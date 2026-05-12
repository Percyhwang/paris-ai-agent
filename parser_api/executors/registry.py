from parser_api.executors.base import BaseExecutor
from parser_api.intents import Intent


class ExecutorRegistry:
    def __init__(self) -> None:
        self._executors: dict[Intent, BaseExecutor] = {}

    def register(self, executor: BaseExecutor) -> None:
        self._executors[executor.intent] = executor

    def get(self, intent: Intent) -> BaseExecutor | None:
        return self._executors.get(intent)

    def has(self, intent: Intent) -> bool:
        return intent in self._executors


def build_default_executor_registry() -> ExecutorRegistry:
    from parser_api.executors.stub import (
        StubIntentExecutor,
    )

    registry = ExecutorRegistry()
    try:
        from parser_api.executors.fastmcp import FastMcpExecutor
    except ModuleNotFoundError:
        from parser_api.executors.localmcp import LocalMcpExecutor

        executor_cls = LocalMcpExecutor
    else:
        executor_cls = FastMcpExecutor

    registry.register(
        executor_cls(
            intent=Intent.CREATE_PLAN,
            service_name="planning",
            tool_name="create_plan",
        )
    )
    registry.register(
        executor_cls(
            intent=Intent.MODIFY_PLAN,
            service_name="planning",
            tool_name="modify_plan",
        )
    )
    registry.register(
        executor_cls(
            intent=Intent.ESTIMATE_BUDGET,
            service_name="discovery",
            tool_name="estimate_budget",
        )
    )
    registry.register(
        executor_cls(
            intent=Intent.OPTIMIZE_ROUTE,
            service_name="discovery",
            tool_name="optimize_route",
        )
    )
    registry.register(
        executor_cls(
            intent=Intent.RECOMMEND_VENUE,
            service_name="discovery",
            tool_name="recommend_venue",
        )
    )
    registry.register(
        executor_cls(
            intent=Intent.MANAGE_TRIP,
            service_name="planning",
            tool_name="manage_trip",
        )
    )
    registry.register(
        executor_cls(
            intent=Intent.USER_PROFILE,
            service_name="profile",
            tool_name="user_profile",
        )
    )
    registry.register(
        executor_cls(
            intent=Intent.TRAVEL_STYLE,
            service_name="profile",
            tool_name="travel_style",
        )
    )
    registry.register(
        executor_cls(
            intent=Intent.TRIP_DIARY,
            service_name="planning",
            tool_name="trip_diary",
        )
    )

    for intent in (
        Intent.FLIGHT_SEARCH,
        Intent.HOTEL_SEARCH,
        Intent.FLIGHT_BOOK,
        Intent.HOTEL_BOOK,
        Intent.MANAGE_BOOKING,
    ):
        registry.register(StubIntentExecutor(intent=intent))

    return registry


executor_registry = build_default_executor_registry()
