import { FormEvent, useEffect, useState } from "react";
import { Card } from "../components/common/Card";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingState } from "../components/common/LoadingState";
import { PageContainer } from "../components/common/PageContainer";
import { TripSelector } from "../components/common/TripSelector";
import { useTripSelection } from "../hooks/useTripSelection";
import { reservationService, type ReservationCreatePayload } from "../services/reservationService";
import { useLanguage } from "../store/LanguageContext";
import type { Reservation } from "../types";
import { formatCurrency, formatDate } from "../utils/format";

const initialForm: ReservationCreatePayload = {
  reservation_type: "hotel",
  provider: "",
  title: "",
  start_date: "",
  end_date: "",
  price: 0,
  currency: "EUR",
  status: "pending",
  booking_reference: "",
};

const RESERVATION_COPY = {
  ko: {
    eyebrow: "예약",
    title: "예약 관리",
    description: "항공권, 호텔, 티켓, 액티비티 예약 정보를 저장하고 상태를 추적합니다.",
    loading: "예약 정보를 불러오는 중입니다",
    loadError: "예약 정보를 불러오지 못했습니다.",
    saveError: "예약 정보를 저장하지 못했습니다.",
    noTripsTitle: "예약을 연결할 여행이 없습니다",
    noTripsDescription: "먼저 메인에서 여행 계획을 생성해 주세요.",
    formTitle: "예약 추가",
    providerPlaceholder: "예약처",
    titlePlaceholder: "예약명",
    amountPlaceholder: "금액",
    bookingReferencePlaceholder: "예약번호 (선택)",
    save: "예약 저장",
    emptyTitle: "저장된 예약이 없습니다",
    emptyDescription: "호텔이나 항공권 정보를 직접 추가해 보세요.",
    types: {
      hotel: "호텔",
      flight: "항공권",
      ticket: "티켓",
      activity: "액티비티",
    },
    statuses: {
      pending: "대기",
      confirmed: "확정",
      canceled: "취소",
    },
  },
  en: {
    eyebrow: "Reservations",
    title: "Reservation Manager",
    description: "Save flights, hotels, tickets, and activity bookings, then track their status.",
    loading: "Loading reservations...",
    loadError: "Could not load reservation details.",
    saveError: "Could not save the reservation.",
    noTripsTitle: "No trip is available for reservations",
    noTripsDescription: "Create a trip plan from the home page first.",
    formTitle: "Add Reservation",
    providerPlaceholder: "Provider",
    titlePlaceholder: "Reservation name",
    amountPlaceholder: "Amount",
    bookingReferencePlaceholder: "Booking reference (optional)",
    save: "Save reservation",
    emptyTitle: "No reservations saved",
    emptyDescription: "Add hotel, flight, ticket, or activity details here.",
    types: {
      hotel: "Hotel",
      flight: "Flight",
      ticket: "Ticket",
      activity: "Activity",
    },
    statuses: {
      pending: "Pending",
      confirmed: "Confirmed",
      canceled: "Canceled",
    },
  },
} as const;

export function ReservationPage() {
  const { language } = useLanguage();
  const copy = RESERVATION_COPY[language];
  const { trips, selectedTripId, setSelectedTripId, isLoading: isTripLoading } = useTripSelection();
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [form, setForm] = useState<ReservationCreatePayload>(initialForm);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedTripId) return;
    loadReservations(selectedTripId);
  }, [selectedTripId]);

  async function loadReservations(tripId: string) {
    setIsLoading(true);
    setError(null);
    try {
      setReservations(await reservationService.listReservations(tripId));
    } catch (err) {
      setError(err instanceof Error ? err.message : copy.loadError);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!selectedTripId) return;
    setError(null);
    try {
      const created = await reservationService.createReservation(selectedTripId, form);
      setReservations((current) => [created, ...current]);
      setForm(initialForm);
    } catch (err) {
      setError(err instanceof Error ? err.message : copy.saveError);
    }
  }

  return (
    <PageContainer
      eyebrow={copy.eyebrow}
      title={copy.title}
      description={copy.description}
      theme="reservation"
      action={<TripSelector trips={trips} selectedTripId={selectedTripId} onChange={setSelectedTripId} />}
    >
      {isTripLoading || isLoading ? <LoadingState label={copy.loading} /> : null}
      {error ? <p className="form-error">{error}</p> : null}
      {!isTripLoading && !trips.length ? <EmptyState title={copy.noTripsTitle} description={copy.noTripsDescription} /> : null}
      {selectedTripId ? (
        <div className="two-column-layout">
          <Card>
            <h2>{copy.formTitle}</h2>
            <form className="stacked-form" onSubmit={handleSubmit}>
              <select value={form.reservation_type} onChange={(event) => setForm({ ...form, reservation_type: event.target.value as ReservationCreatePayload["reservation_type"] })}>
                <option value="hotel">{copy.types.hotel}</option>
                <option value="flight">{copy.types.flight}</option>
                <option value="ticket">{copy.types.ticket}</option>
                <option value="activity">{copy.types.activity}</option>
              </select>
              <input value={form.provider} onChange={(event) => setForm({ ...form, provider: event.target.value })} placeholder={copy.providerPlaceholder} required />
              <input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} placeholder={copy.titlePlaceholder} required />
              <div className="form-row">
                <input type="date" value={form.start_date ?? ""} onChange={(event) => setForm({ ...form, start_date: event.target.value })} />
                <input type="date" value={form.end_date ?? ""} onChange={(event) => setForm({ ...form, end_date: event.target.value })} />
              </div>
              <div className="form-row">
                <input type="number" min="0" value={form.price} onChange={(event) => setForm({ ...form, price: Number(event.target.value) })} placeholder={copy.amountPlaceholder} />
                <input value={form.currency} onChange={(event) => setForm({ ...form, currency: event.target.value.toUpperCase() })} placeholder="EUR" />
              </div>
              <select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as ReservationCreatePayload["status"] })}>
                <option value="pending">{copy.statuses.pending}</option>
                <option value="confirmed">{copy.statuses.confirmed}</option>
                <option value="canceled">{copy.statuses.canceled}</option>
              </select>
              <input
                value={form.booking_reference ?? ""}
                onChange={(event) => setForm({ ...form, booking_reference: event.target.value })}
                placeholder={copy.bookingReferencePlaceholder}
              />
              <button type="submit" className="primary-button">
                {copy.save}
              </button>
            </form>
          </Card>
          <section className="reservation-list">
            {reservations.length ? (
              reservations.map((reservation) => (
                <Card key={reservation.id} className="reservation-card">
                  <div>
                    <span className={`status-pill ${reservation.status}`}>{copy.statuses[reservation.status]}</span>
                    <h3>{reservation.title}</h3>
                    <p>
                      {reservation.provider} · {copy.types[reservation.reservation_type]}
                    </p>
                  </div>
                  <div className="info-strip">
                    <span>
                      {formatDate(reservation.start_date, language)} - {formatDate(reservation.end_date, language)}
                    </span>
                    <span>{formatCurrency(reservation.price, reservation.currency, language)}</span>
                    {reservation.booking_reference ? <span>{reservation.booking_reference}</span> : null}
                  </div>
                </Card>
              ))
            ) : (
              <EmptyState title={copy.emptyTitle} description={copy.emptyDescription} />
            )}
          </section>
        </div>
      ) : null}
    </PageContainer>
  );
}
