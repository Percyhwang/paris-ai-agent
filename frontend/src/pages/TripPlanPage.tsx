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
import { useLanguage } from "../store/LanguageContext";
import type { Trip } from "../types";
import { formatDate } from "../utils/format";

const TRIP_PLAN_COPY = {
  ko: {
    eyebrow: "여행 일정",
    title: "AI 여행 계획 타임라인",
    description: "일자별 일정과 지도 동선을 한눈에 확인하고, 이후 수정과 저장 흐름으로 확장할 수 있는 화면입니다.",
    loading: "여행 일정을 불러오는 중입니다",
    noTripsTitle: "아직 생성된 여행 계획이 없습니다",
    noTripsDescription: "메인 페이지에서 자연어로 원하는 파리 여행을 입력하면 일정이 생성됩니다.",
    createTrip: "여행 계획 만들기",
    routeFallback: "저장된 동선 요약이 없습니다.",
    emptyDayTitle: "일정이 비어 있습니다",
    emptyDayDescription: "itinerary API로 일정을 저장하면 여기에 표시됩니다.",
    day: "Day",
  },
  en: {
    eyebrow: "Itinerary",
    title: "AI Trip Plan Timeline",
    description: "Review each day, route notes, and mapped stops in one place.",
    loading: "Loading itinerary...",
    noTripsTitle: "No trip plans yet",
    noTripsDescription: "Create a Paris trip from the home page with a natural-language request.",
    createTrip: "Create trip plan",
    routeFallback: "No route summary has been saved yet.",
    emptyDayTitle: "This day is empty",
    emptyDayDescription: "Saved itinerary items from the API will appear here.",
    day: "Day",
  },
} as const;

export function TripPlanPage() {
  const { language } = useLanguage();
  const copy = TRIP_PLAN_COPY[language];
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
      eyebrow={copy.eyebrow}
      title={copy.title}
      description={copy.description}
      theme="trip"
      action={<TripSelector trips={trips} selectedTripId={selectedTripId} onChange={setSelectedTripId} />}
    >
      {isTripListLoading || isLoading ? <LoadingState label={copy.loading} /> : null}
      {error ? <p className="form-error">{error}</p> : null}
      {!isTripListLoading && !trips.length ? (
        <EmptyState
          title={copy.noTripsTitle}
          description={copy.noTripsDescription}
          action={
            <Link className="primary-button as-link" to="/">
              {copy.createTrip}
            </Link>
          }
        />
      ) : null}
      {trip ? (
        <div className="trip-layout">
          <section className="trip-main">
            <div className="trip-title-card">
              <span>
                {formatDate(trip.start_date, language)} - {formatDate(trip.end_date, language)}
              </span>
              <h2>{trip.trip_title}</h2>
              <p>{trip.route_summary ?? copy.routeFallback}</p>
              <div className="tag-row">
                {trip.style_tags.map((tag) => (
                  <span key={tag}>#{tag}</span>
                ))}
              </div>
            </div>
            <div className="day-tabs">
              {trip.itinerary_days.map((day, index) => (
                <button key={day.id ?? day.day_number} type="button" className={activeDay === index ? "active" : ""} onClick={() => setActiveDay(index)}>
                  {copy.day} {day.day_number}
                </button>
              ))}
            </div>
            {selectedDay ? (
              <>
                <div className="section-heading">
                  <h2>{selectedDay.title}</h2>
                  <p>
                    {formatDate(selectedDay.date, language)} · {selectedDay.route_summary ?? copy.routeFallback}
                  </p>
                </div>
                <Timeline day={selectedDay} />
              </>
            ) : (
              <EmptyState title={copy.emptyDayTitle} description={copy.emptyDayDescription} />
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
