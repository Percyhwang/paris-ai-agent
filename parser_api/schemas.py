from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from parser_api.intents import Intent


class Destination(BaseModel):
    city: str = "Paris"
    country: str = "FR"


class LocationRef(BaseModel):
    city: Optional[str] = None
    country: Optional[str] = None
    airport_code: Optional[str] = None
    area: Optional[str] = None
    landmark: Optional[str] = None


class Dates(BaseModel):
    start_date: Optional[str] = None  # ISO8601 string (YYYY-MM-DD) or null
    end_date: Optional[str] = None
    days: Optional[int] = Field(default=None, ge=1)
    source: Literal["explicit", "missing"] = "missing"


class Party(BaseModel):
    adult: int = Field(default=0, ge=0)
    highschool: int = Field(default=0, ge=0)
    middleschool: int = Field(default=0, ge=0)
    elementary: int = Field(default=0, ge=0)
    toddler: int = Field(default=0, ge=0)
    trip_style: Literal["solo", "couple", "friends", "family", "unknown"] = "unknown"

    @property
    def total(self) -> int:
        return (
            self.adult
            + self.highschool
            + self.middleschool
            + self.elementary
            + self.toddler
        )


class Lodging(BaseModel):
    text: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


class Mobility(BaseModel):
    travel_mode: Literal["walk", "transit", "both"] = "both"
    optimize: Literal["min_time", "min_transfers"] = "min_time"
    max_walk_km_per_day: Optional[int] = None
    wheelchair: bool = False
    stroller: bool = False


class Pace(BaseModel):
    level: Literal["slow", "normal", "fast"] = "normal"
    max_places_per_day: int = 6


class Budget(BaseModel):
    currency: str = "EUR"
    budget_total: Optional[int] = None
    budget_per_day: Optional[int] = None
    budget_mode: Literal["save", "normal", "flex"] = "normal"


class PreferencesWeights(BaseModel):
    cafe: float = 0.5
    museum: float = 0.5
    park: float = 0.5
    shopping: float = 0.5
    night_view: float = 0.5


class Preferences(BaseModel):
    weights: PreferencesWeights = Field(default_factory=PreferencesWeights)
    themes: List[str] = Field(default_factory=list)
    must_include: List[str] = Field(default_factory=list)
    must_avoid: List[str] = Field(default_factory=list)


class Constraints(BaseModel):
    museum_per_day: Optional[int] = None
    indoor_focus: bool = False
    rainy_plan: bool = False


class OutputOptions(BaseModel):
    include_map: bool = True
    include_excel: bool = True
    include_cost: bool = True


class Clarify(BaseModel):
    needed: bool = False
    missing_fields: List[str] = Field(default_factory=list)


class SharedContextPayload(BaseModel):
    origin: LocationRef = Field(default_factory=LocationRef)
    destination: LocationRef = Field(default_factory=LocationRef)
    dates: Dates = Field(default_factory=Dates)
    party: Party = Field(default_factory=Party)
    budget: Budget = Field(default_factory=Budget)
    trip_id: Optional[str] = None
    clarify: Clarify = Field(default_factory=Clarify)


class CreatePlanPayload(BaseModel):
    intent: Literal["CREATE_PLAN"] = Intent.CREATE_PLAN.value
    destination: Destination = Field(default_factory=Destination)
    dates: Dates = Field(default_factory=Dates)
    party: Party = Field(default_factory=Party)
    lodging: Lodging = Field(default_factory=Lodging)
    mobility: Mobility = Field(default_factory=Mobility)
    pace: Pace = Field(default_factory=Pace)
    budget: Budget = Field(default_factory=Budget)
    preferences: Preferences = Field(default_factory=Preferences)
    constraints: Constraints = Field(default_factory=Constraints)
    output: OutputOptions = Field(default_factory=OutputOptions)
    clarify: Clarify = Field(default_factory=Clarify)


class Operation(BaseModel):
    op: Literal[
        "add",
        "remove",
        "replace",
        "swap",
        "move",
        "set_constraint",
        "set_pace",
        "set_mobility",
        "set_quantity",
    ]
    target_day: Optional[int] = Field(default=None, ge=1)
    target_slot: Optional[Literal["morning", "lunch", "afternoon", "dinner", "night"]] = None
    swap_slots: Optional[List[Literal["morning", "lunch", "afternoon", "dinner", "night"]]] = None
    category: Optional[str] = None
    place_name: Optional[str] = None
    quantity: Optional[int] = Field(default=None, ge=1)
    from_quantity: Optional[int] = Field(default=None, ge=1)
    to_quantity: Optional[int] = Field(default=None, ge=1)
    constraints_patch: Optional[Dict[str, Any]] = None
    pace: Optional[Literal["slow", "normal", "fast"]] = None
    mobility: Optional[Dict[str, Any]] = None


class ModifyPlanPayload(BaseModel):
    intent: Literal["MODIFY_PLAN"] = Intent.MODIFY_PLAN.value
    trip_id: Optional[str] = None
    operations: List[Operation] = Field(default_factory=list)
    clarify: Clarify = Field(default_factory=Clarify)


class RequestBundleAction(BaseModel):
    intent: Literal[
        "CREATE_PLAN",
        "MODIFY_PLAN",
        "FLIGHT_SEARCH",
        "FLIGHT_BOOK",
        "HOTEL_SEARCH",
        "HOTEL_BOOK",
        "ESTIMATE_BUDGET",
        "MANAGE_BOOKING",
        "OPTIMIZE_ROUTE",
        "RECOMMEND_VENUE",
        "MANAGE_TRIP",
        "USER_PROFILE",
        "TRAVEL_STYLE",
        "TRIP_DIARY",
    ]
    order: int = Field(ge=1)
    depends_on: List[str] = Field(default_factory=list)


class RequestBundlePayload(BaseModel):
    intent: Literal["REQUEST_BUNDLE"] = Intent.REQUEST_BUNDLE.value
    shared_context: SharedContextPayload = Field(default_factory=SharedContextPayload)
    actions: List[RequestBundleAction] = Field(default_factory=list)
    clarify: Clarify = Field(default_factory=Clarify)


class FlightSearchPayload(BaseModel):
    intent: Literal["FLIGHT_SEARCH"] = Intent.FLIGHT_SEARCH.value
    origin: LocationRef = Field(default_factory=LocationRef)
    destination: LocationRef = Field(default_factory=LocationRef)
    departure_date: Optional[str] = None
    return_date: Optional[str] = None
    trip_type: Literal["one_way", "round_trip"] = "round_trip"
    cabin_class: Literal["economy", "premium_economy", "business", "first"] = "economy"
    direct_only: bool = False
    party: Party = Field(default_factory=Party)
    max_price: Optional[int] = Field(default=None, ge=0)
    currency: str = "KRW"
    clarify: Clarify = Field(default_factory=Clarify)


class FlightBookPayload(BaseModel):
    intent: Literal["FLIGHT_BOOK"] = Intent.FLIGHT_BOOK.value
    origin: LocationRef = Field(default_factory=LocationRef)
    destination: LocationRef = Field(default_factory=LocationRef)
    departure_date: Optional[str] = None
    return_date: Optional[str] = None
    trip_type: Literal["one_way", "round_trip"] = "round_trip"
    cabin_class: Literal["economy", "premium_economy", "business", "first"] = "economy"
    direct_only: bool = False
    party: Party = Field(default_factory=Party)
    max_price: Optional[int] = Field(default=None, ge=0)
    currency: str = "KRW"
    offer_ref: Optional[str] = None
    requires_confirmation: bool = True
    clarify: Clarify = Field(default_factory=Clarify)


class HotelSearchPayload(BaseModel):
    intent: Literal["HOTEL_SEARCH"] = Intent.HOTEL_SEARCH.value
    destination: LocationRef = Field(default_factory=LocationRef)
    area: Optional[str] = None
    landmark: Optional[str] = None
    check_in_date: Optional[str] = None
    check_out_date: Optional[str] = None
    nights: Optional[int] = Field(default=None, ge=1)
    guests: int = Field(default=1, ge=1)
    rooms: int = Field(default=1, ge=1)
    star_rating: Optional[int] = Field(default=None, ge=1, le=5)
    max_price_per_night: Optional[int] = Field(default=None, ge=0)
    currency: str = "KRW"
    clarify: Clarify = Field(default_factory=Clarify)


class HotelBookPayload(BaseModel):
    intent: Literal["HOTEL_BOOK"] = Intent.HOTEL_BOOK.value
    destination: LocationRef = Field(default_factory=LocationRef)
    area: Optional[str] = None
    landmark: Optional[str] = None
    check_in_date: Optional[str] = None
    check_out_date: Optional[str] = None
    nights: Optional[int] = Field(default=None, ge=1)
    guests: int = Field(default=1, ge=1)
    rooms: int = Field(default=1, ge=1)
    star_rating: Optional[int] = Field(default=None, ge=1, le=5)
    max_price_per_night: Optional[int] = Field(default=None, ge=0)
    currency: str = "KRW"
    property_ref: Optional[str] = None
    requires_confirmation: bool = True
    clarify: Clarify = Field(default_factory=Clarify)


class BudgetComponents(BaseModel):
    flight: bool = True
    hotel: bool = True
    food: bool = True
    transport: bool = True
    activities: bool = True
    shopping: bool = False


class EstimateBudgetPayload(BaseModel):
    intent: Literal["ESTIMATE_BUDGET"] = Intent.ESTIMATE_BUDGET.value
    origin: LocationRef = Field(default_factory=LocationRef)
    destination: LocationRef = Field(default_factory=LocationRef)
    dates: Dates = Field(default_factory=Dates)
    party: Party = Field(default_factory=Party)
    budget: Budget = Field(default_factory=Budget)
    components: BudgetComponents = Field(default_factory=BudgetComponents)
    hotel_star_rating: Optional[int] = Field(default=None, ge=1, le=5)
    clarify: Clarify = Field(default_factory=Clarify)


class BookingChangeRequest(BaseModel):
    check_in_date: Optional[str] = None
    check_out_date: Optional[str] = None
    departure_date: Optional[str] = None
    return_date: Optional[str] = None
    guests: Optional[int] = Field(default=None, ge=1)
    rooms: Optional[int] = Field(default=None, ge=1)
    star_rating: Optional[int] = Field(default=None, ge=1, le=5)
    area: Optional[str] = None
    landmark: Optional[str] = None
    notes: Optional[str] = None


class ManageBookingPayload(BaseModel):
    intent: Literal["MANAGE_BOOKING"] = Intent.MANAGE_BOOKING.value
    operation: Literal["retrieve", "modify", "cancel"] = "retrieve"
    booking_domain: Literal["flight", "hotel", "mixed", "unknown"] = "unknown"
    booking_id: Optional[str] = None
    trip_id: Optional[str] = None
    change_request: BookingChangeRequest = Field(default_factory=BookingChangeRequest)
    requires_confirmation: bool = False
    clarify: Clarify = Field(default_factory=Clarify)


class RoutePoint(BaseModel):
    name: str
    category: Optional[str] = None


class OptimizeRoutePayload(BaseModel):
    intent: Literal["OPTIMIZE_ROUTE"] = Intent.OPTIMIZE_ROUTE.value
    trip_id: Optional[str] = None
    target_day: Optional[int] = Field(default=None, ge=1)
    route_points: List[RoutePoint] = Field(default_factory=list)
    start_location: LocationRef = Field(default_factory=LocationRef)
    end_location: LocationRef = Field(default_factory=LocationRef)
    travel_mode: Literal["walk", "transit", "both"] = "both"
    optimize: Literal["min_time", "min_distance", "min_walking", "min_transfers"] = "min_time"
    clarify: Clarify = Field(default_factory=Clarify)


class RecommendVenuePayload(BaseModel):
    intent: Literal["RECOMMEND_VENUE"] = Intent.RECOMMEND_VENUE.value
    venue_type: Literal["attraction", "restaurant", "cafe", "mixed"] = "attraction"
    destination: LocationRef = Field(default_factory=LocationRef)
    area: Optional[str] = None
    landmark: Optional[str] = None
    party: Party = Field(default_factory=Party)
    budget: Budget = Field(default_factory=Budget)
    themes: List[str] = Field(default_factory=list)
    must_include: List[str] = Field(default_factory=list)
    must_avoid: List[str] = Field(default_factory=list)
    count: int = Field(default=3, ge=1, le=20)
    clarify: Clarify = Field(default_factory=Clarify)


class ManageTripPayload(BaseModel):
    intent: Literal["MANAGE_TRIP"] = Intent.MANAGE_TRIP.value
    operation: Literal["save", "retrieve", "list", "rename", "delete"] = "retrieve"
    trip_id: Optional[str] = None
    trip_title: Optional[str] = None
    scope: Literal["current", "saved", "all", "recent"] = "current"
    clarify: Clarify = Field(default_factory=Clarify)


class UserProfilePreferences(BaseModel):
    trip_style: Optional[Literal["solo", "couple", "friends", "family", "unknown"]] = None
    pace_level: Optional[Literal["slow", "normal", "fast"]] = None
    budget_mode: Optional[Literal["save", "normal", "flex"]] = None
    travel_mode: Optional[Literal["walk", "transit", "both"]] = None
    preferred_themes: List[str] = Field(default_factory=list)
    preferred_areas: List[str] = Field(default_factory=list)
    preferred_landmarks: List[str] = Field(default_factory=list)
    accommodation_star_rating: Optional[int] = Field(default=None, ge=1, le=5)
    food_preferences: List[str] = Field(default_factory=list)
    avoid_preferences: List[str] = Field(default_factory=list)


class UserProfilePayload(BaseModel):
    intent: Literal["USER_PROFILE"] = Intent.USER_PROFILE.value
    operation: Literal["retrieve", "update"] = "update"
    profile: UserProfilePreferences = Field(default_factory=UserProfilePreferences)
    clarify: Clarify = Field(default_factory=Clarify)


class TravelStylePayload(BaseModel):
    intent: Literal["TRAVEL_STYLE"] = Intent.TRAVEL_STYLE.value
    style_tags: List[str] = Field(default_factory=list)
    trip_style: Optional[Literal["solo", "couple", "friends", "family", "unknown"]] = None
    pace_level: Optional[Literal["slow", "normal", "fast"]] = None
    budget_mode: Optional[Literal["save", "normal", "flex"]] = None
    travel_mode: Optional[Literal["walk", "transit", "both"]] = None
    venue_focus: List[str] = Field(default_factory=list)
    clarify: Clarify = Field(default_factory=Clarify)


class TripDiaryPayload(BaseModel):
    intent: Literal["TRIP_DIARY"] = Intent.TRIP_DIARY.value
    operation: Literal["generate"] = "generate"
    trip_id: Optional[str] = None
    target_day: Optional[int] = Field(default=None, ge=1)
    entry_date: Optional[str] = None
    tone: Literal["casual", "emotional", "informative", "blog"] = "casual"
    format: Literal["paragraph", "bullet", "timeline"] = "paragraph"
    include_weather: bool = False
    include_cost: bool = False
    highlights: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    clarify: Clarify = Field(default_factory=Clarify)


class AgentRunRequest(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None


class AgentRunResponse(BaseModel):
    status: Literal["ASK", "DONE", "PARTIAL", "ERROR"]
    intent: str
    trip_id: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)
    clarify: Clarify = Field(default_factory=Clarify)


class GoogleLoginRequest(BaseModel):
    credential: str


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class ApiErrorPayload(BaseModel):
    code: str
    details: Optional[Any] = None


class UserPreferencesPayload(BaseModel):
    travel_style: List[str] = Field(default_factory=list)
    favorite_categories: List[str] = Field(default_factory=list)
    budget_currency: str = "EUR"
    language: str = "ko"


class AuthUserPayload(BaseModel):
    id: str
    google_id: str
    email: str
    name: str
    profile_image: Optional[str] = None
    preferences: UserPreferencesPayload = Field(default_factory=UserPreferencesPayload)
    trips: List[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class TokenPairPayload(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class AuthResponsePayload(BaseModel):
    user: AuthUserPayload
    tokens: TokenPairPayload
