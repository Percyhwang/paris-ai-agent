import asyncio

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.api.deps import get_current_user
from app.core.responses import api_ok
from app.db.mongodb import get_optional_database
from app.services.flight_recommend_service import recommend_flights
from app.services.kiwi_service import city_to_iata, search_flights, search_price_calendar
from app.services.agent_orchestrator_service import orchestrate_flight_search

router = APIRouter()


@router.post("/recommend")
async def recommend_flights_route(
    body: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_optional_database),
) -> dict:
    query = str(body.get("query") or "").strip()
    trip_id = body.get("trip_id")
    if not query:
        raise HTTPException(status_code=400, detail="query field is required")
    async def execute_search() -> dict:
        try:
            return await asyncio.to_thread(recommend_flights, query)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    result = await orchestrate_flight_search(
        user_request=query,
        trip_id=trip_id,
        db=db,
        user_id=current_user["id"],
        execute_search=execute_search,
    )
    return api_ok(result)


@router.get("/search")
async def search_flights_route(
    origin: str = Query(..., description="Origin city or IATA code"),
    destination: str = Query(..., description="Destination city or IATA code"),
    departure_date: str = Query(..., description="Departure date YYYY-MM-DD"),
    return_date: str | None = Query(None, description="Return date YYYY-MM-DD"),
    adults: int = Query(1, ge=1, le=9),
    currency: str = Query("KRW"),
    limit: int = Query(5, ge=1, le=20),
    trip_id: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_optional_database),
) -> dict:
    origin_iata = city_to_iata(origin)
    destination_iata = city_to_iata(destination)
    if not origin_iata:
        raise HTTPException(status_code=400, detail=f"Could not resolve origin IATA code: {origin}")
    if not destination_iata:
        raise HTTPException(status_code=400, detail=f"Could not resolve destination IATA code: {destination}")
    async def execute_search() -> dict:
        try:
            flights = await asyncio.to_thread(
                search_flights,
                fly_from=origin_iata,
                fly_to=destination_iata,
                departure_date=departure_date,
                return_date=return_date,
                adults=adults,
                currency=currency,
                limit=limit,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "flights": flights,
            "count": len(flights),
            "search_conditions": {
                "origin": origin,
                "destination": destination,
                "departure_date": departure_date,
                "return_date": return_date,
                "adults": adults,
                "currency": currency,
            },
        }

    result = await orchestrate_flight_search(
        user_request=f"Search flights from {origin} to {destination} on {departure_date}",
        trip_id=trip_id,
        db=db,
        user_id=current_user["id"],
        execute_search=execute_search,
    )
    return api_ok(result)


@router.get("/price-calendar")
def price_calendar_route(
    origin: str = Query(...),
    destination: str = Query(...),
    month: str = Query(..., description="YYYY-MM"),
    adults: int = Query(1, ge=1),
    currency: str = Query("KRW"),
    _: dict = Depends(get_current_user),
) -> dict:
    origin_iata = city_to_iata(origin)
    destination_iata = city_to_iata(destination)
    if not origin_iata:
        raise HTTPException(status_code=400, detail=f"Could not resolve origin IATA code: {origin}")
    if not destination_iata:
        raise HTTPException(status_code=400, detail=f"Could not resolve destination IATA code: {destination}")
    try:
        calendar = search_price_calendar(
            fly_from=origin_iata,
            fly_to=destination_iata,
            month=month,
            adults=adults,
            currency=currency,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return api_ok(calendar)
