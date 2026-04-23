import { useEffect, useState } from "react";
import { tripService } from "../services/tripService";
import type { Trip } from "../types";

export function useTripSelection(initialTripId?: string) {
  const [trips, setTrips] = useState<Trip[]>([]);
  const [selectedTripId, setSelectedTripId] = useState<string | undefined>(initialTripId);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadTrips() {
    setIsLoading(true);
    setError(null);
    try {
      const data = await tripService.listTrips();
      setTrips(data);
      setSelectedTripId((current) => current || initialTripId || data[0]?.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "여행 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadTrips();
  }, [initialTripId]);

  const selectedTrip = trips.find((trip) => trip.id === selectedTripId);

  return {
    trips,
    selectedTrip,
    selectedTripId,
    setSelectedTripId,
    isLoading,
    error,
    reloadTrips: loadTrips,
  };
}
