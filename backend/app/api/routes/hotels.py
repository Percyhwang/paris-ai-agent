import asyncio

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.api.deps import get_current_user
from app.core.responses import api_ok
from app.db.mongodb import get_optional_database
from app.services.booking_service import get_room_list, search_destination, search_hotels
from app.services.hotel_recommend_service import recommend_hotels
from app.services.agent_orchestrator_service import orchestrate_hotel_search

router = APIRouter()


@router.post("/recommend")
async def recommend_hotels_route(
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
            return await asyncio.to_thread(recommend_hotels, query)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    result = await orchestrate_hotel_search(
        user_request=query,
        trip_id=trip_id,
        db=db,
        user_id=current_user["id"],
        execute_search=execute_search,
    )
    return api_ok(result)


@router.get("/search")
async def search_hotels_route(
    destination: str = Query(..., description="City name, e.g. Paris"),
    checkin: str = Query(..., description="Check-in date YYYY-MM-DD"),
    checkout: str = Query(..., description="Check-out date YYYY-MM-DD"),
    adults: int = Query(1, ge=1, le=9),
    currency: str = Query("KRW"),
    language: str = Query("ko"),
    limit: int = Query(10, ge=1, le=30),
    trip_id: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_optional_database),
) -> dict:
    async def execute_search() -> dict:
        try:
            dest_id = await asyncio.to_thread(search_destination, destination)
            if not dest_id:
                raise HTTPException(status_code=404, detail=f"Could not resolve hotel destination: {destination}")
            hotels = await asyncio.to_thread(
                search_hotels,
                dest_id=dest_id,
                checkin=checkin,
                checkout=checkout,
                adults=adults,
                currency=currency,
                language=language,
                limit=limit,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "hotels": hotels,
            "count": len(hotels),
            "destId": dest_id,
            "search_conditions": {
                "destination": destination,
                "checkin": checkin,
                "checkout": checkout,
                "adults": adults,
                "currency": currency,
            },
        }

    result = await orchestrate_hotel_search(
        user_request=f"Search hotels in {destination} from {checkin} to {checkout}",
        trip_id=trip_id,
        db=db,
        user_id=current_user["id"],
        execute_search=execute_search,
    )
    return api_ok(result)


@router.get("/{hotel_id}/rooms")
def get_rooms_route(
    hotel_id: str,
    checkin: str = Query(...),
    checkout: str = Query(...),
    adults: int = Query(1, ge=1),
    currency: str = Query("KRW"),
    language: str = Query("ko"),
    _: dict = Depends(get_current_user),
) -> dict:
    try:
        rooms = get_room_list(
            hotel_id=hotel_id,
            checkin=checkin,
            checkout=checkout,
            adults=adults,
            currency=currency,
            language=language,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return api_ok({"rooms": rooms, "count": len(rooms)})
