import { apiRequest } from "./apiClient";

export interface FlightRecommendation extends Flight {
  rank: number;
  reason: string;
}

export interface RecommendFlightsResult {
  flights: FlightRecommendation[];
  flight_candidates?: FlightRecommendation[];
  parsedParams: {
    origin: string;
    destination: string;
    departure_date: string;
    return_date: string | null;
    adults: number;
    currency: string;
    preferences: string[];
  };
  count: number;
  trip_id?: string | null;
  agent_summary?: string;
  ranking_reason?: string[];
  ranking_summary?: Record<string, unknown>;
  search_conditions?: Record<string, unknown>;
  warnings?: string[];
  frontend_display?: Record<string, unknown>;
}

export interface Flight {
  id: string;
  price: number;
  deepLink: string | null;
  flyFrom: string;
  flyFromCity: string;
  flyTo: string;
  flyToCity: string;
  departure: string;
  arrival: string;
  durationHours: number;
  stops: number;
  airlines: string[];
  airlineNames: string[];
  returnDeparture?: string;
  returnArrival?: string;
  returnDurationHours?: number;
  returnStops?: number;
  segments?: FlightSegment[];
  returnSegments?: FlightSegment[];
}

export interface FlightSegment {
  from: string;
  fromCity: string;
  to: string;
  toCity: string;
  departure: string;
  arrival: string;
}

export interface PriceCalendar {
  month: string;
  currency: string;
  days: { date: string; price: number }[];
  cheapestDate: string | null;
  cheapestPrice: number | null;
}

export async function recommendFlights(query: string): Promise<RecommendFlightsResult> {
  return apiRequest("/flights/recommend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
}

export async function searchFlights(params: {
  origin: string;
  destination: string;
  departure_date: string;
  return_date?: string;
  adults?: number;
  currency?: string;
  limit?: number;
}): Promise<{ flights: Flight[]; flight_candidates?: Flight[]; count: number; warnings?: string[]; frontend_display?: Record<string, unknown> }> {
  const query = new URLSearchParams();
  query.set("origin", params.origin);
  query.set("destination", params.destination);
  query.set("departure_date", params.departure_date);
  if (params.return_date) query.set("return_date", params.return_date);
  if (params.adults) query.set("adults", String(params.adults));
  if (params.currency) query.set("currency", params.currency);
  if (params.limit) query.set("limit", String(params.limit));
  return apiRequest(`/flights/search?${query}`);
}

export async function fetchPriceCalendar(params: {
  origin: string;
  destination: string;
  month: string;
  adults?: number;
  currency?: string;
}): Promise<PriceCalendar> {
  const query = new URLSearchParams();
  query.set("origin", params.origin);
  query.set("destination", params.destination);
  query.set("month", params.month);
  if (params.adults) query.set("adults", String(params.adults));
  if (params.currency) query.set("currency", params.currency);
  return apiRequest(`/flights/price-calendar?${query}`);
}
