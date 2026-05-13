from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user
from app.core.responses import api_ok
from app.services.booking_service import get_room_list, search_destination, search_hotels

router = APIRouter()


@router.get("/search")
def search_hotels_route(
    destination: str = Query(..., description="도시명 (영문 권장, 예: Paris)"),
    checkin: str = Query(..., description="체크인 YYYY-MM-DD"),
    checkout: str = Query(..., description="체크아웃 YYYY-MM-DD"),
    adults: int = Query(1, ge=1, le=9),
    currency: str = Query("KRW"),
    language: str = Query("ko"),
    limit: int = Query(10, ge=1, le=30),
    _: dict = Depends(get_current_user),
) -> dict:
    try:
        dest_id = search_destination(destination)
        if not dest_id:
            raise HTTPException(status_code=404, detail=f"'{destination}' 의 dest_id를 찾을 수 없습니다.")
        hotels = search_hotels(
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
    return api_ok({"hotels": hotels, "count": len(hotels), "destId": dest_id})


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
