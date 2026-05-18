import { apiRequest } from "./apiClient";
import type { ItineraryDay, Trip, TripGenerateRequest, TripGenerationJob } from "../types";

export const tripService = {
  startTripGeneration(payload: TripGenerateRequest): Promise<TripGenerationJob> {
    return apiRequest<TripGenerationJob>("/trips/generate/jobs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getTripGenerationJob(jobId: string): Promise<TripGenerationJob> {
    return apiRequest<TripGenerationJob>(`/trips/generate/jobs/${jobId}`);
  },

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

  modifyTripWithAgent(tripId: string, payload: { prompt: string; target_day?: number | null }): Promise<Trip> {
    return apiRequest<Trip>(`/trips/${tripId}/agent-modify`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  deleteTrip(tripId: string): Promise<{ deleted: boolean }> {
    return apiRequest<{ deleted: boolean }>(`/trips/${tripId}`, {
      method: "DELETE",
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
