import requests

from app.core.config import settings


def _headers() -> dict:
    return {
        "X-RapidAPI-Key": settings.rapidapi_key or "",
        "X-RapidAPI-Host": settings.booking_rapidapi_host,
    }


def _get(path: str, params: dict) -> dict:
    host = settings.booking_rapidapi_host
    response = requests.get(f"https://{host}{path}", headers=_headers(), params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def search_destination(city: str) -> str | None:
    data = _get("/api/v1/hotels/searchDestination", {"query": city})
    results = data.get("data", [])
    if not results:
        return None
    return results[0].get("dest_id")


def _normalize_hotel(raw: dict) -> dict:
    prop = raw.get("property", {})
    gross = prop.get("priceBreakdown", {}).get("grossPrice", {})
    price_amount = gross.get("value")
    hotel_id = raw.get("hotel_id") or prop.get("id")
    checkin = prop.get("checkinDate", "")
    checkout = prop.get("checkoutDate", "")
    deep_link = (
        f"https://www.booking.com/searchresults.html"
        f"?dest_id={hotel_id}&dest_type=hotel&checkin={checkin}&checkout={checkout}"
    ) if hotel_id else None
    return {
        "hotelId": hotel_id,
        "name": prop.get("name"),
        "reviewScore": prop.get("reviewScore"),
        "reviewScoreWord": prop.get("reviewScoreWord"),
        "reviewCount": prop.get("reviewCount"),
        "stars": prop.get("propertyClass"),
        "price": round(price_amount) if price_amount else None,
        "currency": gross.get("currency", "KRW"),
        "checkin": checkin,
        "checkout": checkout,
        "latitude": prop.get("latitude"),
        "longitude": prop.get("longitude"),
        "photoUrl": prop.get("photoUrls", [None])[0],
        "deepLink": deep_link,
    }


def search_hotels(
    dest_id: str,
    checkin: str,
    checkout: str,
    adults: int = 1,
    currency: str = "KRW",
    language: str = "ko",
    limit: int = 10,
) -> list[dict]:
    params = {
        "dest_id": dest_id,
        "search_type": "CITY",
        "arrival_date": checkin,
        "departure_date": checkout,
        "adults": adults,
        "currency_code": currency,
        "languagecode": language,
        "page_number": 1,
        "units": "metric",
    }
    data = _get("/api/v1/hotels/searchHotels", params)
    hotels_raw = data.get("data", {}).get("hotels", [])
    return [_normalize_hotel(h) for h in hotels_raw[:limit]]


def get_room_list(
    hotel_id: str | int,
    checkin: str,
    checkout: str,
    adults: int = 1,
    currency: str = "KRW",
    language: str = "ko",
) -> list[dict]:
    params = {
        "hotel_id": hotel_id,
        "arrival_date": checkin,
        "departure_date": checkout,
        "adults": adults,
        "currency_code": currency,
        "languagecode": language,
        "units": "metric",
    }
    data = _get("/api/v1/hotels/getRoomListWithAvailability", params)
    result = []
    for room in data.get("available", []):
        price_breakdown = room.get("product_price_breakdown", {})
        gross = price_breakdown.get("gross_amount_per_night") or price_breakdown.get("gross_amount", {})
        price_value = gross.get("value") if isinstance(gross, dict) else None
        highlights = [h.get("translated_name", "") for h in room.get("bh_room_highlights", []) if h.get("translated_name")]
        result.append({
            "roomId": room.get("room_id"),
            "roomName": room.get("room_name") or room.get("name"),
            "maxOccupancy": room.get("max_occupancy"),
            "price": round(float(price_value)) if price_value else None,
            "currency": currency,
            "breakfastIncluded": bool(room.get("breakfast_included")),
            "freeCancellation": bool(room.get("refundable")),
            "payLater": bool(room.get("choose_when_you_pay")),
            "highlights": highlights,
        })
    return result
