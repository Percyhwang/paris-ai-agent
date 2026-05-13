import { useLanguage } from "../../store/LanguageContext";
import type { Trip } from "../../types";

type TripSelectorProps = {
  trips: Trip[];
  selectedTripId?: string;
  onChange: (tripId: string) => void;
  disabled?: boolean;
};

export function TripSelector({ trips, selectedTripId, onChange, disabled = false }: TripSelectorProps) {
  const { language } = useLanguage();

  if (!trips.length) return null;

  return (
    <label className="trip-selector">
      <span>{language === "en" ? "Select trip" : "여행 선택"}</span>
      <select value={selectedTripId ?? ""} onChange={(event) => onChange(event.target.value)} disabled={disabled}>
        {trips.map((trip) => (
          <option key={trip.id} value={trip.id}>
            {trip.trip_title}
          </option>
        ))}
      </select>
    </label>
  );
}
