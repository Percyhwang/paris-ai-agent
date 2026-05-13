import { FormEvent, useState } from "react";
import { PageContainer } from "../components/common/PageContainer";
import { useTripSelection } from "../hooks/useTripSelection";
import { useLanguage } from "../store/LanguageContext";

const COPY = {
  ko: {
    eyebrow: "Stay",
    title: "숙소 검색",
    description: "Booking.com API 연결 전까지는 여행 일정과 조건을 정리하는 검색 준비 화면입니다.",
    destination: "도착지",
    checkIn: "체크인",
    checkOut: "체크아웃",
    guests: "인원",
    rooms: "객실",
    budget: "1박 예산",
    search: "검색 조건 저장",
    ready: "Booking.com API 키가 연결되면 이 조건으로 실시간 숙소를 조회합니다.",
  },
  en: {
    eyebrow: "Stay",
    title: "Accommodation Search",
    description: "A booking-ready search workspace until the Booking.com API is connected.",
    destination: "Destination",
    checkIn: "Check-in",
    checkOut: "Check-out",
    guests: "Guests",
    rooms: "Rooms",
    budget: "Nightly budget",
    search: "Save search",
    ready: "Once the Booking.com API is connected, these filters can run a live hotel search.",
  },
} as const;

export function AccommodationSearchPage() {
  const { language } = useLanguage();
  const copy = COPY[language];
  const { selectedTripId } = useTripSelection();
  const [saved, setSaved] = useState(false);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSaved(true);
  }

  return (
    <PageContainer eyebrow={copy.eyebrow} title={copy.title} description={copy.description} theme="reservation">
      <section className="search-workspace">
        <form className="stacked-form search-panel" onSubmit={handleSubmit}>
          <div className="form-row">
            <label>
              {copy.destination}
              <input defaultValue="Paris" />
            </label>
            <label>
              {copy.budget}
              <input type="number" min="0" placeholder="180" />
            </label>
          </div>
          <div className="form-row">
            <label>
              {copy.checkIn}
              <input type="date" />
            </label>
            <label>
              {copy.checkOut}
              <input type="date" />
            </label>
          </div>
          <div className="form-row">
            <label>
              {copy.guests}
              <input type="number" min="1" defaultValue="2" />
            </label>
            <label>
              {copy.rooms}
              <input type="number" min="1" defaultValue="1" />
            </label>
          </div>
          <button type="submit" className="primary-button">
            {copy.search}
          </button>
        </form>
        <div className="search-placeholder">
          <strong>{copy.ready}</strong>
          <span>{selectedTripId ? `trip_id: ${selectedTripId}` : "No trip selected"}</span>
          {saved ? <span>Search preferences saved locally for this session.</span> : null}
        </div>
      </section>
    </PageContainer>
  );
}
