import { apiRequest } from "./apiClient";
import type { ItineraryDay, Trip, TripGenerateRequest } from "../types";

export const tripService = {
  generateTrip(payload: TripGenerateRequest): Promise<Trip> {
    return apiRequest<Trip>("/trips/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  createTrip(payload: { trip_title: string; total_days: number; start_date?: string; end_date?: string; style_tags?: string[] }): Promise<Trip> {
    return apiRequest<Trip>("/trips", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  listTrips(): Promise<Trip[]> {
    return apiRequest<Trip[]>("/trips");
  },

  getTrip(tripId: string): Promise<Trip> {
    return apiRequest<Trip>(`/trips/${tripId}`);
  },

  updateTrip(tripId: string, payload: Partial<Trip>): Promise<Trip> {
    return apiRequest<Trip>(`/trips/${tripId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  getItinerary(tripId: string): Promise<ItineraryDay[]> {
    return apiRequest<ItineraryDay[]>(`/trips/${tripId}/itinerary`);
  },

  updateItinerary(tripId: string, days: ItineraryDay[]): Promise<ItineraryDay[]> {
    return apiRequest<ItineraryDay[]>(`/trips/${tripId}/itinerary`, {
      method: "PUT",
      body: JSON.stringify({ days }),
    });
  },
};
