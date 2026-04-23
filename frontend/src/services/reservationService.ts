import { apiRequest } from "./apiClient";
import type { Reservation } from "../types";

export type ReservationCreatePayload = Omit<Reservation, "id" | "trip_id" | "user_id" | "created_at" | "updated_at">;

export const reservationService = {
  listReservations(tripId: string): Promise<Reservation[]> {
    return apiRequest<Reservation[]>(`/trips/${tripId}/reservations`);
  },

  createReservation(tripId: string, payload: ReservationCreatePayload): Promise<Reservation> {
    return apiRequest<Reservation>(`/trips/${tripId}/reservations`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};
