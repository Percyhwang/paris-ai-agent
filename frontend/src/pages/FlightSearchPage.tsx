import { FormEvent, useState } from "react";
import { PageContainer } from "../components/common/PageContainer";
import { useLanguage } from "../store/LanguageContext";
import { fetchPriceCalendar, searchFlights, type Flight, type PriceCalendar } from "../services/flightService";

const COPY = {
  ko: {
    eyebrow: "Flights",
    title: "항공권 검색",
    description: "Kiwi.com API로 실시간 항공권을 조회합니다.",
    from: "출발지",
    to: "도착지",
    depart: "출발일",
    returnDate: "귀국일 (편도면 비워두세요)",
    passengers: "탑승객 수",
    search: "항공권 검색",
    calendarBtn: "월별 최저가 보기",
    loading: "검색 중...",
    noResults: "검색 결과가 없습니다.",
    stops: (n: number) => (n === 0 ? "직항" : `경유 ${n}회`),
    book: "예약하기 →",
    cheapest: "이 달 최저가",
    direct: "직항",
  },
  en: {
    eyebrow: "Flights",
    title: "Flight Search",
    description: "Search real-time flights via Kiwi.com API.",
    from: "From",
    to: "To",
    depart: "Depart",
    returnDate: "Return (leave blank for one-way)",
    passengers: "Passengers",
    search: "Search Flights",
    calendarBtn: "Monthly prices",
    loading: "Searching...",
    noResults: "No results found.",
    stops: (n: number) => (n === 0 ? "Direct" : `${n} stop${n > 1 ? "s" : ""}`),
    book: "Book →",
    cheapest: "Cheapest this month",
    direct: "Direct",
  },
} as const;

const fmt = (price: number | null) =>
  price == null ? "—" : price.toLocaleString("ko-KR") + "원";

export function FlightSearchPage() {
  const { language } = useLanguage();
  const copy = COPY[language];

  const [origin, setOrigin] = useState("서울");
  const [destination, setDestination] = useState("Paris");
  const [departureDate, setDepartureDate] = useState("");
  const [returnDate, setReturnDate] = useState("");
  const [adults, setAdults] = useState(1);

  const [flights, setFlights] = useState<Flight[]>([]);
  const [calendar, setCalendar] = useState<PriceCalendar | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setCalendar(null);
    try {
      const result = await searchFlights({
        origin,
        destination,
        departure_date: departureDate,
        return_date: returnDate || undefined,
        adults,
      });
      setFlights(result.flights);
      if (result.flights.length === 0) setError(copy.noResults);
    } catch (err) {
      setError(err instanceof Error ? err.message : "검색에 실패했습니다.");
      setFlights([]);
    } finally {
      setLoading(false);
    }
  }

  async function handleCalendar() {
    if (!departureDate) return;
    setLoading(true);
    setError(null);
    setFlights([]);
    try {
      const result = await fetchPriceCalendar({
        origin,
        destination,
        month: departureDate.slice(0, 7),
        adults,
      });
      setCalendar(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "캘린더 조회에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageContainer eyebrow={copy.eyebrow} title={copy.title} description={copy.description} theme="reservation">
      <div className="search-workspace">

        {/* ── 검색 폼 ── */}
        <form className="booking-search-panel stacked-form" onSubmit={handleSearch}>
          <div className="form-row">
            <label>
              {copy.from}
              <input value={origin} onChange={(e) => setOrigin(e.target.value)} placeholder="서울" required />
            </label>
            <label>
              {copy.to}
              <input value={destination} onChange={(e) => setDestination(e.target.value)} placeholder="Paris" required />
            </label>
          </div>
          <div className="form-row">
            <label>
              {copy.depart}
              <input type="date" value={departureDate} onChange={(e) => setDepartureDate(e.target.value)} required />
            </label>
            <label>
              {copy.returnDate}
              <input type="date" value={returnDate} onChange={(e) => setReturnDate(e.target.value)} />
            </label>
          </div>
          <label style={{ maxWidth: 160 }}>
            {copy.passengers}
            <input type="number" min="1" max="9" value={adults} onChange={(e) => setAdults(Number(e.target.value))} />
          </label>
          <div className="booking-search-actions">
            <button type="submit" className="primary-button" disabled={loading}>
              {loading ? copy.loading : copy.search}
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={handleCalendar}
              disabled={loading || !departureDate}
            >
              {copy.calendarBtn}
            </button>
          </div>
        </form>

        {error && <p className="error-message">{error}</p>}

        {/* ── 최저가 캘린더 ── */}
        {calendar && (
          <div className="calendar-panel">
            <p className="calendar-cheapest-note">
              ✦&nbsp;{copy.cheapest}:&nbsp;
              <strong>{calendar.cheapestDate}</strong>&nbsp;—&nbsp;{fmt(calendar.cheapestPrice)}
            </p>
            <div className="calendar-grid">
              {calendar.days.map((d) => (
                <div
                  key={d.date}
                  className={`calendar-cell${d.date === calendar.cheapestDate ? " cheapest" : ""}`}
                >
                  <span className="cal-date">{d.date.slice(5)}</span>
                  <span className="cal-price">{fmt(d.price)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── 항공권 결과 ── */}
        {flights.length > 0 && (
          <ul className="results-panel flight-list">
            {flights.map((f) => (
              <li key={f.id} className="flight-card">
                <div className="flight-route">
                  <span>{f.flyFromCity ?? f.flyFrom} → {f.flyToCity ?? f.flyTo}</span>
                  <span className="flight-duration">{f.durationHours}h · {copy.stops(f.stops)}</span>
                </div>
                <div className="flight-times">
                  {f.departure} → {f.arrival}
                  {f.returnDeparture && (
                    <span className="flight-return">
                      &nbsp;·&nbsp;귀국 {f.returnDeparture} → {f.returnArrival}
                    </span>
                  )}
                </div>
                <div className="flight-airline">{f.airlineNames.join(" · ")}</div>
                <div className="flight-footer">
                  <strong className="flight-price">{fmt(f.price)}</strong>
                  {f.deepLink && (
                    <a href={f.deepLink} target="_blank" rel="noopener noreferrer" className="book-link">
                      {copy.book}
                    </a>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}

      </div>
    </PageContainer>
  );
}
