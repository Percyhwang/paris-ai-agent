from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user
from app.core.responses import api_ok
from app.services.kiwi_service import city_to_iata, search_flights, search_price_calendar

router = APIRouter()


@router.get("/search")
def search_flights_route(
    origin: str = Query(..., description="출발 도시 (한글 또는 IATA 코드)"),
    destination: str = Query(..., description="도착 도시 (한글 또는 영문)"),
    departure_date: str = Query(..., description="출발일 YYYY-MM-DD"),
    return_date: str | None = Query(None, description="귀국일 YYYY-MM-DD (편도면 생략)"),
    adults: int = Query(1, ge=1, le=9),
    currency: str = Query("KRW"),
    limit: int = Query(5, ge=1, le=20),
    _: dict = Depends(get_current_user),
) -> dict:
    origin_iata = city_to_iata(origin) or origin.upper()
    destination_iata = city_to_iata(destination) or city_to_iata(destination.lower())
    if not destination_iata:
        raise HTTPException(status_code=400, detail=f"목적지 IATA 코드를 찾을 수 없습니다: {destination}")
    try:
        flights = search_flights(
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
    return api_ok({"flights": flights, "count": len(flights)})


@router.get("/price-calendar")
def price_calendar_route(
    origin: str = Query(...),
    destination: str = Query(...),
    month: str = Query(..., description="YYYY-MM"),
    adults: int = Query(1, ge=1),
    currency: str = Query("KRW"),
    _: dict = Depends(get_current_user),
) -> dict:
    origin_iata = city_to_iata(origin) or origin.upper()
    destination_iata = city_to_iata(destination) or city_to_iata(destination.lower())
    if not destination_iata:
        raise HTTPException(status_code=400, detail=f"목적지 IATA 코드를 찾을 수 없습니다: {destination}")
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
