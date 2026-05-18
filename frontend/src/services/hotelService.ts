import { apiRequest } from "./apiClient";

export interface HotelRecommendation extends Hotel {
  rank: number;
  reason: string;
  _distKm?: number;
}

export interface RecommendHotelsResult {
  hotels: HotelRecommendation[];
  hotel_candidates?: HotelRecommendation[];
  parsedParams: {
    destination: string;
    checkin: string;
    checkout: string;
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

export interface Hotel {
  hotelId: string | number;
  name: string;
  reviewScore: number | null;
  reviewScoreWord: string | null;
  reviewCount: number | null;
  stars: number | null;
  price: number | null;
  currency: string;
  checkin: string;
  checkout: string;
  latitude: number | null;
  longitude: number | null;
  photoUrl: string | null;
  deepLink: string | null;
}

export interface Room {
  roomId: string;
  roomName: string;
  maxOccupancy: number | null;
  price: number | null;
  currency: string;
  breakfastIncluded: boolean;
  freeCancellation: boolean;
  payLater: boolean;
  highlights: string[];
}

export async function searchHotels(params: {
  destination: string;
  checkin: string;
  checkout: string;
  adults?: number;
  currency?: string;
  language?: string;
  limit?: number;
}): Promise<{ hotels: Hotel[]; hotel_candidates?: Hotel[]; count: number; destId: string; warnings?: string[]; frontend_display?: Record<string, unknown> }> {
  const query = new URLSearchParams();
  query.set("destination", params.destination);
  query.set("checkin", params.checkin);
  query.set("checkout", params.checkout);
  if (params.adults) query.set("adults", String(params.adults));
  if (params.currency) query.set("currency", params.currency);
  if (params.language) query.set("language", params.language);
  if (params.limit) query.set("limit", String(params.limit));
  return apiRequest(`/hotels/search?${query}`);
}

export async function recommendHotels(query: string): Promise<RecommendHotelsResult> {
  return apiRequest("/hotels/recommend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
}

export async function fetchRooms(
  hotelId: string | number,
  params: { checkin: string; checkout: string; adults?: number; currency?: string }
): Promise<{ rooms: Room[]; count: number }> {
  const query = new URLSearchParams();
  query.set("checkin", params.checkin);
  query.set("checkout", params.checkout);
  if (params.adults) query.set("adults", String(params.adults));
  if (params.currency) query.set("currency", params.currency);
  return apiRequest(`/hotels/${hotelId}/rooms?${query}`);
}
