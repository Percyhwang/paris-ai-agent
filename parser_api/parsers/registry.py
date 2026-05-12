from parser_api.intents import Intent
from parser_api.parsers.base import BaseParser


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[Intent, BaseParser] = {}

    def register(self, parser: BaseParser) -> None:
        self._parsers[parser.intent] = parser

    def get(self, intent: Intent) -> BaseParser | None:
        return self._parsers.get(intent)

    def has(self, intent: Intent) -> bool:
        return intent in self._parsers

    def registered_intents(self) -> tuple[Intent, ...]:
        return tuple(self._parsers.keys())


def build_default_parser_registry() -> ParserRegistry:
    registry = ParserRegistry()

    from parser_api.parsers.create_plan.parser import CreatePlanParser
    from parser_api.parsers.estimate_budget.parser import EstimateBudgetParser
    from parser_api.parsers.flight_book.parser import FlightBookParser
    from parser_api.parsers.flight_search.parser import FlightSearchParser
    from parser_api.parsers.hotel_book.parser import HotelBookParser
    from parser_api.parsers.hotel_search.parser import HotelSearchParser
    from parser_api.parsers.manage_booking.parser import ManageBookingParser
    from parser_api.parsers.manage_trip.parser import ManageTripParser
    from parser_api.parsers.modify_plan.parser import ModifyPlanParser
    from parser_api.parsers.optimize_route.parser import OptimizeRouteParser
    from parser_api.parsers.recommend_venue.parser import RecommendVenueParser
    from parser_api.parsers.travel_style.parser import TravelStyleParser
    from parser_api.parsers.trip_diary.parser import TripDiaryParser
    from parser_api.parsers.user_profile.parser import UserProfileParser
    from parser_api.parsers.workflow.request_bundle.parser import RequestBundleParser

    registry.register(RequestBundleParser())
    registry.register(CreatePlanParser())
    registry.register(ModifyPlanParser())
    registry.register(FlightSearchParser())
    registry.register(FlightBookParser())
    registry.register(HotelSearchParser())
    registry.register(HotelBookParser())
    registry.register(EstimateBudgetParser())
    registry.register(ManageBookingParser())
    registry.register(ManageTripParser())
    registry.register(OptimizeRouteParser())
    registry.register(RecommendVenueParser())
    registry.register(UserProfileParser())
    registry.register(TravelStyleParser())
    registry.register(TripDiaryParser())
    return registry


parser_registry = build_default_parser_registry()
