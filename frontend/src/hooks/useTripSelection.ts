import { useEffect, useState } from "react";
import { tripService } from "../services/tripService";
import { useLanguage } from "../store/LanguageContext";
import type { Trip } from "../types";

export function useTripSelection(initialTripId?: string) {
  const { language } = useLanguage();
  const [trips, setTrips] = useState<Trip[]>([]);
  const [selectedTripId, setSelectedTripId] = useState<string | undefined>(initialTripId);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadTrips(nextSelectedId?: string | null) {
    setIsLoading(true);
    setError(null);
    try {
      const data = await tripService.listTrips();
      setTrips(data);
      setSelectedTripId((current) => {
        if (nextSelectedId !== undefined) {
          return nextSelectedId ?? undefined;
        }
        if (current && data.some((trip) => trip.id === current)) {
          return current;
        }
        if (initialTripId && data.some((trip) => trip.id === initialTripId)) {
          return initialTripId;
        }
        return data[0]?.id;
      });
    } catch (err) {
      if (err instanceof Error && err.message === "Database unavailable") {
        setTrips([]);
        setSelectedTripId(undefined);
        setError(null);
        return;
      }
      setError(err instanceof Error ? err.message : language === "en" ? "Could not load your trips." : "여행 목록을 불러오지 못했습니다.");
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
