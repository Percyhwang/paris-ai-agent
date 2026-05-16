import { FormEvent, useEffect, useState } from "react";
import { TripHotelSection } from "../components/trip/TripHotelSection";
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
    edit: "수정",
    delete: "삭제",
    save: "저장",
    saving: "저장 중",
    deleting: "삭제 중",
    cancel: "취소",
    titleLabel: "여행 이름",
    startDateLabel: "시작일",
    endDateLabel: "종료일",
    tagsLabel: "스타일 태그",
    tagsPlaceholder: "감성, 미술관, 야경",
    updateError: "여행 계획을 수정하지 못했습니다.",
    deleteError: "여행 계획을 삭제하지 못했습니다.",
    deleteConfirm: '"{title}" 여행 계획을 삭제할까요?',
    agentEditTitle: "Agent 수정 요청",
    agentEditPlaceholder: "예: 2일차 루브르 대신 오르세 넣어줘",
    agentEditSubmit: "Agent로 수정",
    agentEditing: "Agent가 수정 중",
    agentEditSuccess: "Agent가 여행 일정을 수정했습니다.",
    agentEditError: "Agent가 여행 일정을 수정하지 못했습니다.",
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
    edit: "Edit",
    delete: "Delete",
    save: "Save",
    saving: "Saving",
    deleting: "Deleting",
    cancel: "Cancel",
    titleLabel: "Trip name",
    startDateLabel: "Start date",
    endDateLabel: "End date",
    tagsLabel: "Style tags",
    tagsPlaceholder: "museums, slow travel, night views",
    updateError: "Could not update this trip plan.",
    deleteError: "Could not delete this trip plan.",
    deleteConfirm: 'Delete "{title}"?',
    agentEditTitle: "Agent Edit Request",
    agentEditPlaceholder: "E.g. Replace the Louvre with Orsay on day 2",
    agentEditSubmit: "Edit with Agent",
    agentEditing: "Agent is editing",
    agentEditSuccess: "The agent updated your itinerary.",
    agentEditError: "The agent could not update your itinerary.",
  },
} as const;

function toDateInputValue(value?: string | null) {
  return value ? value.slice(0, 10) : "";
}

export function TripPlanPage() {
  const { language } = useLanguage();
  const copy = TRIP_PLAN_COPY[language];
  const { tripId } = useParams();
  const { trips, selectedTripId, setSelectedTripId, isLoading: isTripListLoading, error, reloadTrips } = useTripSelection(tripId);
  const [trip, setTrip] = useState<Trip | null>(null);
  const [activeDay, setActiveDay] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editStartDate, setEditStartDate] = useState("");
  const [editEndDate, setEditEndDate] = useState("");
  const [editStyleTags, setEditStyleTags] = useState("");
  const [agentPrompt, setAgentPrompt] = useState("");
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [mutationNote, setMutationNote] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isAgentEditing, setIsAgentEditing] = useState(false);
  const isMutating = isSaving || isDeleting || isAgentEditing;

  useEffect(() => {
    if (!selectedTripId) {
      setTrip(null);
      setActiveDay(0);
      setIsEditing(false);
      return;
    }
    const currentTripId = selectedTripId;
    let mounted = true;
    async function loadTrip() {
      setIsLoading(true);
      try {
        const data = await tripService.getTrip(currentTripId);
        if (mounted) {
          setTrip(data);
          setActiveDay(0);
          setIsEditing(false);
          setMutationError(null);
          setMutationNote(null);
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

  function fillEditForm(currentTrip: Trip) {
    setEditTitle(currentTrip.trip_title);
    setEditStartDate(toDateInputValue(currentTrip.start_date));
    setEditEndDate(toDateInputValue(currentTrip.end_date));
    setEditStyleTags(currentTrip.style_tags.join(", "));
  }

  function handleStartEdit() {
    if (!trip) return;
    fillEditForm(trip);
    setMutationError(null);
    setMutationNote(null);
    setIsEditing(true);
  }

  async function handleSaveTrip(event: FormEvent) {
    event.preventDefault();
    if (!trip || !selectedTripId || !editTitle.trim()) return;

    setIsSaving(true);
    setMutationError(null);
    setMutationNote(null);
    try {
      const updatedTrip = await tripService.updateTrip(selectedTripId, {
        trip_title: editTitle.trim(),
        start_date: editStartDate || null,
        end_date: editEndDate || null,
        style_tags: editStyleTags
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
      });
      setTrip(updatedTrip);
      setIsEditing(false);
      await reloadTrips(updatedTrip.id);
    } catch (err) {
      setMutationError(err instanceof Error ? err.message : copy.updateError);
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDeleteTrip() {
    if (!trip || !selectedTripId) return;
    const confirmed = window.confirm(copy.deleteConfirm.replace("{title}", trip.trip_title));
    if (!confirmed) return;

    setIsDeleting(true);
    setMutationError(null);
    setMutationNote(null);
    try {
      await tripService.deleteTrip(selectedTripId);
      const nextTripId = trips.find((candidate) => candidate.id !== selectedTripId)?.id ?? null;
      setTrip(null);
      setSelectedTripId(nextTripId ?? undefined);
      await reloadTrips(nextTripId);
    } catch (err) {
      setMutationError(err instanceof Error ? err.message : copy.deleteError);
    } finally {
      setIsDeleting(false);
    }
  }

  async function handleAgentEditSubmit(event: FormEvent) {
    event.preventDefault();
    if (!trip || !selectedTripId || !agentPrompt.trim()) return;

    setIsAgentEditing(true);
    setMutationError(null);
    setMutationNote(null);
    try {
      const updatedTrip = await tripService.modifyTripWithAgent(selectedTripId, {
        prompt: agentPrompt.trim(),
        target_day: selectedDay?.day_number ?? activeDay + 1,
      });
      setTrip(updatedTrip);
      setAgentPrompt("");
      setMutationNote(copy.agentEditSuccess);
      await reloadTrips(updatedTrip.id);
    } catch (err) {
      setMutationError(err instanceof Error ? err.message : copy.agentEditError);
    } finally {
      setIsAgentEditing(false);
    }
  }

  const selectedDay = trip?.itinerary_days[activeDay];
  const mapPlaces =
    selectedDay?.items
      .filter(
        (item) =>
          item.itemKind !== "gap" &&
          !item.nearbyMealNeeded &&
          item.place.category !== "meal_placeholder" &&
          item.place.coordinates,
      )
      .map((item) => ({ name: item.place.name, coordinates: item.place.coordinates })) ?? [];

  return (
    <PageContainer
      eyebrow={copy.eyebrow}
      title={copy.title}
      description={copy.description}
      theme="trip"
      action={
        <div className="trip-page-actions">
          <TripSelector trips={trips} selectedTripId={selectedTripId} onChange={setSelectedTripId} disabled={isMutating} />
          {selectedTripId ? (
            <div className="trip-actions">
              <button type="button" className="ghost-button small" onClick={handleStartEdit} disabled={!trip || isMutating}>
                {copy.edit}
              </button>
              <button
                type="button"
                className="ghost-button danger-button small"
                onClick={handleDeleteTrip}
                disabled={!trip || isMutating}
              >
                {isDeleting ? copy.deleting : copy.delete}
              </button>
            </div>
          ) : null}
        </div>
      }
    >
      {isTripListLoading || isLoading ? <LoadingState label={copy.loading} /> : null}
      {error ? <p className="form-error">{error}</p> : null}
      {mutationError ? <p className="form-error">{mutationError}</p> : null}
      {mutationNote ? <p className="success-note">{mutationNote}</p> : null}
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
        <>
        <div className="trip-layout">
          <section className="trip-main">
            <div className="trip-title-card">
              <div className="trip-title-header">
                <span>
                  {formatDate(trip.start_date, language)} - {formatDate(trip.end_date, language)}
                </span>
              </div>
              {isEditing ? (
                <form className="trip-edit-form stacked-form" onSubmit={handleSaveTrip}>
                  <label>
                    {copy.titleLabel}
                    <input value={editTitle} onChange={(event) => setEditTitle(event.target.value)} required />
                  </label>
                  <div className="form-row">
                    <label>
                      {copy.startDateLabel}
                      <input type="date" value={editStartDate} onChange={(event) => setEditStartDate(event.target.value)} />
                    </label>
                    <label>
                      {copy.endDateLabel}
                      <input type="date" value={editEndDate} onChange={(event) => setEditEndDate(event.target.value)} />
                    </label>
                  </div>
                  <label>
                    {copy.tagsLabel}
                    <input value={editStyleTags} onChange={(event) => setEditStyleTags(event.target.value)} placeholder={copy.tagsPlaceholder} />
                  </label>
                  <div className="trip-edit-actions">
                    <button type="submit" className="primary-button small" disabled={isMutating}>
                      {isSaving ? copy.saving : copy.save}
                    </button>
                    <button type="button" className="ghost-button small" onClick={() => setIsEditing(false)} disabled={isMutating}>
                      {copy.cancel}
                    </button>
                  </div>
                </form>
              ) : (
                <>
                  <h2>{trip.trip_title}</h2>
                  <p>{trip.route_summary ?? copy.routeFallback}</p>
                  <div className="tag-row">
                    {trip.style_tags.map((tag) => (
                      <span key={tag}>#{tag}</span>
                    ))}
                  </div>
                </>
              )}
            </div>
            <form className="agent-edit-panel" onSubmit={handleAgentEditSubmit}>
              <label>
                <span>{copy.agentEditTitle}</span>
                <textarea
                  value={agentPrompt}
                  onChange={(event) => setAgentPrompt(event.target.value)}
                  placeholder={copy.agentEditPlaceholder}
                  disabled={isMutating}
                />
              </label>
              <button type="submit" className="primary-button" disabled={isMutating || !agentPrompt.trim()}>
                {isAgentEditing ? copy.agentEditing : copy.agentEditSubmit}
              </button>
            </form>
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
                  <h2>{selectedDay.dayTheme ?? selectedDay.title}</h2>
                  <p>{formatDate(selectedDay.date, language)}</p>
                  {selectedDay.daySummary ? <div className="day-summary-note">{selectedDay.daySummary}</div> : null}
                  <div className="day-route-note">{selectedDay.routeSummary ?? selectedDay.route_summary ?? copy.routeFallback}</div>
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
        <TripHotelSection trip={trip} />
        </>
      ) : null}
    </PageContainer>
  );
}
