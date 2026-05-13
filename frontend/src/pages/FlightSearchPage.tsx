import { FormEvent, useState } from "react";
import { PageContainer } from "../components/common/PageContainer";
import { useLanguage } from "../store/LanguageContext";

const COPY = {
  ko: {
    eyebrow: "Flights",
    title: "항공권 검색",
    description: "Kayak API 연결 전까지 출발지, 일정, 인원 조건을 정리하는 검색 준비 화면입니다.",
    from: "출발지",
    to: "도착지",
    depart: "출발일",
    returnDate: "귀국일",
    passengers: "탑승객",
    cabin: "좌석 등급",
    search: "검색 조건 저장",
    ready: "Kayak API 키가 연결되면 이 조건으로 실시간 항공권을 조회합니다.",
  },
  en: {
    eyebrow: "Flights",
    title: "Flight Search",
    description: "A flight-search workspace until the Kayak API is connected.",
    from: "From",
    to: "To",
    depart: "Depart",
    returnDate: "Return",
    passengers: "Passengers",
    cabin: "Cabin",
    search: "Save search",
    ready: "Once the Kayak API is connected, these filters can run a live flight search.",
  },
} as const;

export function FlightSearchPage() {
  const { language } = useLanguage();
  const copy = COPY[language];
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
              {copy.from}
              <input placeholder="ICN" />
            </label>
            <label>
              {copy.to}
              <input defaultValue="PAR" />
            </label>
          </div>
          <div className="form-row">
            <label>
              {copy.depart}
              <input type="date" />
            </label>
            <label>
              {copy.returnDate}
              <input type="date" />
            </label>
          </div>
          <div className="form-row">
            <label>
              {copy.passengers}
              <input type="number" min="1" defaultValue="1" />
            </label>
            <label>
              {copy.cabin}
              <select defaultValue="economy">
                <option value="economy">Economy</option>
                <option value="premium_economy">Premium Economy</option>
                <option value="business">Business</option>
              </select>
            </label>
          </div>
          <button type="submit" className="primary-button">
            {copy.search}
          </button>
        </form>
        <div className="search-placeholder">
          <strong>{copy.ready}</strong>
          {saved ? <span>Search preferences saved locally for this session.</span> : null}
        </div>
      </section>
    </PageContainer>
  );
}
