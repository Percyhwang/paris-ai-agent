import { FormEvent, useEffect, useState } from "react";
import { Card } from "../components/common/Card";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingState } from "../components/common/LoadingState";
import { PageContainer } from "../components/common/PageContainer";
import { TripSelector } from "../components/common/TripSelector";
import { useTripSelection } from "../hooks/useTripSelection";
import { reservationService, type ReservationCreatePayload } from "../services/reservationService";
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

export function ReservationPage() {
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
      setError(err instanceof Error ? err.message : "예약 정보를 불러오지 못했습니다.");
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
      setError(err instanceof Error ? err.message : "예약 정보를 저장하지 못했습니다.");
    }
  }

  return (
    <PageContainer
      eyebrow="Reservations"
      title="예약 관리"
      description="항공권, 호텔, 액티비티 예약 정보를 저장하고 상태를 추적합니다."
      action={<TripSelector trips={trips} selectedTripId={selectedTripId} onChange={setSelectedTripId} />}
    >
      {isTripLoading || isLoading ? <LoadingState /> : null}
      {error ? <p className="form-error">{error}</p> : null}
      {!isTripLoading && !trips.length ? (
        <EmptyState title="예약을 연결할 여행이 없습니다" description="먼저 메인에서 여행 계획을 생성해 주세요." />
      ) : null}
      {selectedTripId ? (
        <div className="two-column-layout">
          <Card>
            <h2>예약 추가</h2>
            <form className="stacked-form" onSubmit={handleSubmit}>
              <select value={form.reservation_type} onChange={(event) => setForm({ ...form, reservation_type: event.target.value as ReservationCreatePayload["reservation_type"] })}>
                <option value="hotel">호텔</option>
                <option value="flight">항공권</option>
                <option value="ticket">티켓</option>
                <option value="activity">액티비티</option>
              </select>
              <input value={form.provider} onChange={(event) => setForm({ ...form, provider: event.target.value })} placeholder="예약처" required />
              <input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} placeholder="예약명" required />
              <div className="form-row">
                <input type="date" value={form.start_date ?? ""} onChange={(event) => setForm({ ...form, start_date: event.target.value })} />
                <input type="date" value={form.end_date ?? ""} onChange={(event) => setForm({ ...form, end_date: event.target.value })} />
              </div>
              <div className="form-row">
                <input type="number" min="0" value={form.price} onChange={(event) => setForm({ ...form, price: Number(event.target.value) })} placeholder="금액" />
                <input value={form.currency} onChange={(event) => setForm({ ...form, currency: event.target.value.toUpperCase() })} placeholder="EUR" />
              </div>
              <select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as ReservationCreatePayload["status"] })}>
                <option value="pending">pending</option>
                <option value="confirmed">confirmed</option>
                <option value="canceled">canceled</option>
              </select>
              <input value={form.booking_reference ?? ""} onChange={(event) => setForm({ ...form, booking_reference: event.target.value })} placeholder="예약번호 optional" />
              <button type="submit" className="primary-button">예약 저장</button>
            </form>
          </Card>
          <section className="reservation-list">
            {reservations.length ? (
              reservations.map((reservation) => (
                <Card key={reservation.id} className="reservation-card">
                  <div>
                    <span className={`status-pill ${reservation.status}`}>{reservation.status}</span>
                    <h3>{reservation.title}</h3>
                    <p>{reservation.provider} · {reservation.reservation_type}</p>
                  </div>
                  <div className="info-strip">
                    <span>{formatDate(reservation.start_date)} - {formatDate(reservation.end_date)}</span>
                    <span>{formatCurrency(reservation.price, reservation.currency)}</span>
                    {reservation.booking_reference ? <span>{reservation.booking_reference}</span> : null}
                  </div>
                </Card>
              ))
            ) : (
              <EmptyState title="저장된 예약이 없습니다" description="호텔 또는 항공권 정보를 직접 추가해보세요." />
            )}
          </section>
        </div>
      ) : null}
    </PageContainer>
  );
}
