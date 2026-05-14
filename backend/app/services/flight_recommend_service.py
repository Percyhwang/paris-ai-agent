from app.services.kiwi_service import city_to_iata, search_flights
from app.services.llm_service import parse_flight_query, rank_flights


def recommend_flights(query: str) -> dict:
    params = parse_flight_query(query)

    origin_iata = city_to_iata(params.get("origin", "서울")) or params.get("origin", "ICN").upper()
    destination_raw = params.get("destination", "파리")
    destination_iata = city_to_iata(destination_raw) or city_to_iata(destination_raw.lower()) or destination_raw.upper()

    flights = search_flights(
        fly_from=origin_iata,
        fly_to=destination_iata,
        departure_date=params["departure_date"],
        return_date=params.get("return_date") or None,
        adults=params.get("adults", 1),
        currency=params.get("currency", "KRW"),
        limit=20,
    )

    preferences = params.get("preferences", [])
    rankings = rank_flights(flights, preferences)

    flight_map = {str(f["id"]): f for f in flights}
    results = []
    for r in rankings:
        flight = flight_map.get(str(r.get("flightId", "")))
        if flight:
            results.append({**flight, "rank": r["rank"], "reason": r.get("reason", "")})

    return {"flights": results, "parsedParams": params, "count": len(results)}
