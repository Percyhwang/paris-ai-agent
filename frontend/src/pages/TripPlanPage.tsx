import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingState } from "../components/common/LoadingState";
import { PageContainer } from "../components/common/PageContainer";
import { TripSelector } from "../components/common/TripSelector";
import { GoogleMapViewer } from "../components/itinerary/GoogleMapViewer";
import { Timeline } from "../components/itinerary/Timeline";
import { useTripSelection } from "../hooks/useTripSelection";
import { tripService } from "../services/tripService";
import type { Trip } from "../types";
import { formatDate } from "../utils/format";

export function TripPlanPage() {
  const { tripId } = useParams();
  const { trips, selectedTripId, setSelectedTripId, isLoading: isTripListLoading, error } = useTripSelection(tripId);
  const [trip, setTrip] = useState<Trip | null>(null);
  const [activeDay, setActiveDay] = useState(0);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!selectedTripId) return;
    const currentTripId = selectedTripId;
    let mounted = true;
    async function loadTrip() {
      setIsLoading(true);
      try {
        const data = await tripService.getTrip(currentTripId);
        if (mounted) {
          setTrip(data);
          setActiveDay(0);
        }
      } finally {
        if (mounted) setIsLoading(false);
      }
    }
    loadTrip();
    return () => {
      mounted = false;
    };
  }, [selectedTripId]);

  const selectedDay = trip?.itinerary_days[activeDay];
  const mapPlaces = selectedDay?.items.map((item) => ({ name: item.place.name, coordinates: item.place.coordinates })) ?? [];

  return (
    <PageContainer
      eyebrow="Itinerary"
      title="AI 여행 계획 타임라인"
      description="일자별 일정과 지도 동선을 함께 확인하고, 향후 수정/저장 흐름으로 확장할 수 있는 화면입니다."
      action={<TripSelector trips={trips} selectedTripId={selectedTripId} onChange={setSelectedTripId} />}
    >
      {isTripListLoading || isLoading ? <LoadingState /> : null}
      {error ? <p className="form-error">{error}</p> : null}
      {!isTripListLoading && !trips.length ? (
        <EmptyState
          title="아직 생성된 여행 계획이 없습니다"
          description="메인 페이지에서 자연어로 원하는 파리 여행을 입력하면 일정이 생성됩니다."
          action={<Link className="primary-button as-link" to="/">여행 계획 만들기</Link>}
        />
      ) : null}
      {trip ? (
        <div className="trip-layout">
          <section className="trip-main">
            <div className="trip-title-card">
              <span>{formatDate(trip.start_date)} - {formatDate(trip.end_date)}</span>
              <h2>{trip.trip_title}</h2>
              <p>{trip.route_summary ?? "저장된 동선 요약이 없습니다."}</p>
              <div className="tag-row">
                {trip.style_tags.map((tag) => (
                  <span key={tag}>#{tag}</span>
                ))}
              </div>
            </div>
            <div className="day-tabs">
              {trip.itinerary_days.map((day, index) => (
                <button key={day.id ?? day.day_number} type="button" className={activeDay === index ? "active" : ""} onClick={() => setActiveDay(index)}>
                  Day {day.day_number}
                </button>
              ))}
            </div>
            {selectedDay ? (
              <>
                <div className="section-heading">
                  <h2>{selectedDay.title}</h2>
                  <p>{formatDate(selectedDay.date)} · {selectedDay.route_summary}</p>
                </div>
                <Timeline day={selectedDay} />
              </>
            ) : (
              <EmptyState title="일정이 비어 있습니다" description="itinerary API로 일정을 저장하면 이곳에 표시됩니다." />
            )}
          </section>
          <aside className="trip-map">
            <GoogleMapViewer places={mapPlaces} />
          </aside>
        </div>
      ) : null}
    </PageContainer>
  );
}
