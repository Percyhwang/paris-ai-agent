import type { Trip } from "../../types";

type TripSelectorProps = {
  trips: Trip[];
  selectedTripId?: string;
  onChange: (tripId: string) => void;
};

export function TripSelector({ trips, selectedTripId, onChange }: TripSelectorProps) {
  if (!trips.length) return null;

  return (
    <label className="trip-selector">
      <span>여행 선택</span>
      <select value={selectedTripId ?? ""} onChange={(event) => onChange(event.target.value)}>
        {trips.map((trip) => (
          <option key={trip.id} value={trip.id}>
            {trip.trip_title}
          </option>
        ))}
      </select>
    </label>
  );
}
