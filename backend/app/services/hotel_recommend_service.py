from math import atan2, cos, radians, sin, sqrt

from app.services.booking_service import search_destination, search_hotels
from app.services.llm_service import parse_hotel_query, rank_hotels

_LANDMARKS: dict[str, tuple[float, float]] = {
    "에펠탑": (48.8584, 2.2945),
    "루브르": (48.8606, 2.3376),
    "샹젤리제": (48.8698, 2.3078),
    "몽마르트": (48.8867, 2.3431),
    "노트르담": (48.8530, 2.3499),
    "오르세": (48.8600, 2.3266),
    "베르사유": (48.8049, 2.1204),
}

_MAX_NEARBY_KM = 2.5


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi, dlambda = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def _filter_by_landmark(hotels: list[dict], preferences: list[str]) -> list[dict]:
    target: tuple[float, float] | None = None
    for pref in preferences:
        for name, coords in _LANDMARKS.items():
            if name in pref:
                target = coords
                break
        if target:
            break
    if not target:
        return hotels

    nearby = []
    for h in hotels:
        lat, lon = h.get("latitude"), h.get("longitude")
        if lat and lon:
            dist = _haversine_km(float(lat), float(lon), target[0], target[1])
            if dist <= _MAX_NEARBY_KM:
                nearby.append({**h, "_distKm": round(dist, 2)})
    return nearby if nearby else hotels


def recommend_hotels(query: str) -> dict:
    params = parse_hotel_query(query)
    destination = params.get("destination", "Paris")
    dest_id = search_destination(destination)
    if not dest_id:
        raise ValueError(f"'{destination}' 목적지를 찾을 수 없습니다.")

    hotels = search_hotels(
        dest_id=dest_id,
        checkin=params["checkin"],
        checkout=params["checkout"],
        adults=params.get("adults", 2),
        currency=params.get("currency", "KRW"),
        limit=20,
    )

    preferences = params.get("preferences", [])
    filtered = _filter_by_landmark(hotels, preferences)

    rankings = rank_hotels(filtered, preferences)

    hotel_map = {str(h["hotelId"]): h for h in filtered}
    results = []
    for r in rankings:
        hotel = hotel_map.get(str(r.get("hotelId", "")))
        if hotel:
            results.append({**hotel, "rank": r["rank"], "reason": r.get("reason", "")})

    return {"hotels": results, "parsedParams": params, "count": len(results)}
