import { FormEvent, useState } from "react";
import { PageContainer } from "../components/common/PageContainer";
import { useLanguage } from "../store/LanguageContext";
import { recommendFlights, type FlightRecommendation, type FlightSegment } from "../services/flightService";

const COPY = {
  ko: {
    eyebrow: "Flights",
    title: "항공권 추천",
    description: "여행 계획을 자연어로 말씀해 주세요. AI가 최적의 항공권을 추천해 드립니다.",
    placeholder:
      "예: 7월 10일 서울에서 파리로 출발해서 7월 20일에 돌아올거야. 직항이면 좋겠고 성인 2명이야.",
    search: "AI 추천받기",
    loading: "AI가 분석 중입니다...",
    noResults: "조건에 맞는 항공권을 찾지 못했습니다. 다른 조건으로 다시 시도해 보세요.",
    parsedTitle: "AI가 이해한 조건",
    outbound: "가는 편",
    inbound: "오는 편",
    oneway: "편도",
    stops: (n: number) => (n === 0 ? "직항" : `경유 ${n}회`),
    book: "예약하기",
    rank: (n: number) => `추천 ${n}위`,
    whyTitle: "AI 추천 이유",
    departure: "출발",
    returnDate: "귀국",
    adults: "인원",
    total: "총 가격",
  },
  en: {
    eyebrow: "Flights",
    title: "Flight Recommendation",
    description: "Describe your travel plans in natural language. AI will find the best flights.",
    placeholder:
      "e.g. I'm flying from Seoul to Paris on July 10th and returning July 20th. Prefer direct flights, 2 adults.",
    search: "Get AI Recommendations",
    loading: "AI is analyzing your request...",
    noResults: "No flights matched your criteria. Try rephrasing your request.",
    parsedTitle: "What AI understood",
    outbound: "Outbound",
    inbound: "Return",
    oneway: "One-way",
    stops: (n: number) => (n === 0 ? "Direct" : `${n} stop${n > 1 ? "s" : ""}`),
    book: "Book",
    rank: (n: number) => `#${n} Pick`,
    whyTitle: "Why AI recommends this",
    departure: "Depart",
    returnDate: "Return",
    adults: "Passengers",
    total: "Total price",
  },
} as const;

const fmtPrice = (price: number | null) =>
  price == null ? "—" : price.toLocaleString("ko-KR") + "원";

function fmtDateTime(raw: string): string {
  const m = raw.match(/(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (!m) return raw;
  const [, , month, day, hour, min] = m;
  return `${Number(month)}/${Number(day)} ${hour}:${min}`;
}

function SegmentList({ segments }: { segments: FlightSegment[] }) {
  return (
    <div className="flight-segments">
      {segments.map((seg, i) => (
        <div key={i} className="flight-segment-row">
          <div className="flight-segment-cities">
            <span className="flight-segment-city">{seg.fromCity ?? seg.from}</span>
            <span className="flight-segment-arrow">→</span>
            <span className="flight-segment-city">{seg.toCity ?? seg.to}</span>
          </div>
          <span className="flight-segment-times">
            {fmtDateTime(seg.departure)} → {fmtDateTime(seg.arrival)}
          </span>
          {i < segments.length - 1 && (
            <div className="flight-layover-indicator">
              <span className="flight-layover-dot" />
              <span className="flight-layover-label">경유 · {seg.toCity ?? seg.to}</span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export function FlightSearchPage() {
  const { language } = useLanguage();
  const copy = COPY[language];

  const [query, setQuery] = useState("");
  const [flights, setFlights] = useState<FlightRecommendation[]>([]);
  const [parsedParams, setParsedParams] = useState<{
    origin?: string; destination?: string; departure_date?: string;
    return_date?: string | null; adults?: number; preferences?: string[];
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch(e: FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setFlights([]);
    setParsedParams(null);
    try {
      const result = await recommendFlights(query);
      setFlights(result.flights);
      setParsedParams(result.parsedParams);
      if (result.flights.length === 0) setError(copy.noResults);
    } catch (err) {
      setError(err instanceof Error ? err.message : "추천 요청에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageContainer eyebrow={copy.eyebrow} title={copy.title} description={copy.description} theme="reservation">
      <div className="search-workspace">

        {/* ── 자연어 입력 ── */}
        <form className="nl-search-panel" onSubmit={handleSearch}>
          <textarea
            className="nl-search-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={copy.placeholder}
            rows={3}
            required
          />
          <div className="booking-search-actions">
            <button type="submit" className="primary-button" disabled={loading}>
              {loading ? copy.loading : copy.search}
            </button>
          </div>
        </form>

        {error && <p className="error-message">{error}</p>}

        {/* ── AI가 이해한 조건 요약 ── */}
        {parsedParams && !loading && (
          <div className="parsed-params-card">
            <span className="parsed-params-title">{copy.parsedTitle}</span>
            <div className="parsed-params-tags">
              {parsedParams.departure_date && (
                <span className="param-tag">{copy.departure}: {parsedParams.departure_date}</span>
              )}
              {parsedParams.return_date && (
                <span className="param-tag">{copy.returnDate}: {parsedParams.return_date}</span>
              )}
              {parsedParams.adults != null && (
                <span className="param-tag">{copy.adults}: {parsedParams.adults}명</span>
              )}
              {parsedParams.preferences?.map((p) => (
                <span key={p} className="param-tag preference">{p}</span>
              ))}
            </div>
          </div>
        )}

        {/* ── 항공권 결과 ── */}
        {flights.length > 0 && (
          <ul className="results-panel flight-list">
            {flights.map((f) => (
              <li key={f.id} className="flight-card">

                {/* 상단: 순위 + 항공사 */}
                <div className="flight-card-header">
                  <span className="ai-rank-badge">{copy.rank(f.rank)}</span>
                  <span className="flight-airline-name">✈ {f.airlineNames.join(" · ")}</span>
                </div>

                {/* 구간 블록 */}
                <div className="flight-legs">

                  {/* 가는 편 */}
                  <div className="flight-leg">
                    <div className="flight-leg-top">
                      <span className="flight-leg-label outbound">{copy.outbound}</span>
                      <div className="flight-leg-badges">
                        <span className="flight-badge">{f.durationHours}h</span>
                        <span className="flight-badge">{copy.stops(f.stops)}</span>
                      </div>
                    </div>
                    {f.segments ? (
                      <SegmentList segments={f.segments} />
                    ) : (
                      <>
                        <div className="flight-leg-route">
                          <span className="flight-city">{f.flyFromCity ?? f.flyFrom}</span>
                          <span className="flight-arrow">→</span>
                          <span className="flight-city">{f.flyToCity ?? f.flyTo}</span>
                        </div>
                        <span className="flight-time-range">
                          {fmtDateTime(f.departure)} → {fmtDateTime(f.arrival)}
                        </span>
                      </>
                    )}
                  </div>

                  {/* 오는 편 (왕복인 경우) */}
                  {f.returnDeparture && (
                    <>
                      <div className="flight-leg-divider" />
                      <div className="flight-leg">
                        <div className="flight-leg-top">
                          <span className="flight-leg-label inbound">{copy.inbound}</span>
                          <div className="flight-leg-badges">
                            {f.returnDurationHours != null && (
                              <span className="flight-badge">{f.returnDurationHours}h</span>
                            )}
                            {f.returnStops != null && (
                              <span className="flight-badge">{copy.stops(f.returnStops)}</span>
                            )}
                          </div>
                        </div>
                        {f.returnSegments ? (
                          <SegmentList segments={f.returnSegments} />
                        ) : (
                          <>
                            <div className="flight-leg-route">
                              <span className="flight-city">{f.flyToCity ?? f.flyTo}</span>
                              <span className="flight-arrow">→</span>
                              <span className="flight-city">{f.flyFromCity ?? f.flyFrom}</span>
                            </div>
                            <span className="flight-time-range">
                              {fmtDateTime(f.returnDeparture!)} → {fmtDateTime(f.returnArrival!)}
                            </span>
                          </>
                        )}
                      </div>
                    </>
                  )}
                </div>

                {/* AI 추천 이유 */}
                {f.reason && (
                  <div className="ai-reason-box">
                    <span className="ai-reason-label">{copy.whyTitle}</span>
                    <p className="ai-reason-text">{f.reason}</p>
                  </div>
                )}

                {/* 하단: 가격 + 예약 */}
                <div className="flight-footer">
                  <div className="flight-price-wrap">
                    <span className="flight-price-label">{copy.total}</span>
                    <span className="flight-price">{fmtPrice(f.price)}</span>
                  </div>
                  {f.deepLink && (
                    <a href={f.deepLink} target="_blank" rel="noopener noreferrer" className="book-link">
                      {copy.book} →
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
