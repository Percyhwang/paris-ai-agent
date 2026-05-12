from typing import Optional, Protocol, Union, runtime_checkable

from parser_api.intents import Intent
from parser_api.schemas import (
    CreatePlanPayload,
    EstimateBudgetPayload,
    FlightBookPayload,
    FlightSearchPayload,
    HotelBookPayload,
    HotelSearchPayload,
    ManageBookingPayload,
    ManageTripPayload,
    ModifyPlanPayload,
    OptimizeRoutePayload,
    RecommendVenuePayload,
    RequestBundlePayload,
    TravelStylePayload,
    TripDiaryPayload,
    UserProfilePayload,
)

ParsedPayload = Union[
    CreatePlanPayload,
    ModifyPlanPayload,
    FlightSearchPayload,
    FlightBookPayload,
    HotelSearchPayload,
    HotelBookPayload,
    EstimateBudgetPayload,
    ManageBookingPayload,
    ManageTripPayload,
    OptimizeRoutePayload,
    RecommendVenuePayload,
    RequestBundlePayload,
    TravelStylePayload,
    TripDiaryPayload,
    UserProfilePayload,
]


@runtime_checkable
class BaseParser(Protocol):
    intent: Intent

    def parse(self, message: str, context: Optional[dict] = None) -> ParsedPayload:
        ...
