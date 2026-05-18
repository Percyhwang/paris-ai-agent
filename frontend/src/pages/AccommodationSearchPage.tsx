import { FormEvent, useState } from "react";
import { AgentSummaryCard } from "../components/agent/AgentSummaryCard";
import { PageContainer } from "../components/common/PageContainer";
import { useLanguage } from "../store/LanguageContext";
import {
  fetchRooms,
  recommendHotels,
  type HotelRecommendation,
  type Room,
} from "../services/hotelService";

const COPY = {
  ko: {
    eyebrow: "Stay",
    title: "숙소 추천",
    description: "원하는 조건을 자연어로 말씀해 주세요. AI가 최적의 숙소를 추천해 드립니다.",
    placeholder:
      "예: 7월 10일부터 15일까지 파리여행 갈건데 에펠탑 근처, 역세권, 조식포함 호텔 추천해줘. 성인 2명이야.",
    search: "AI 추천받기",
    loading: "AI가 분석 중입니다...",
    noResults: "조건에 맞는 숙소를 찾지 못했습니다. 다른 조건으로 다시 시도해 보세요.",
    parsedTitle: "AI가 이해한 조건",
    book: "Booking.com →",
    viewRooms: "객실 보기",
    hideRooms: "접기",
    breakfast: "조식 포함",
    freeCancellation: "무료 취소",
    payLater: "나중에 결제",
    perNight: "/ 박",
    reviewsCount: (n: number) => `리뷰 ${n.toLocaleString()}개`,
    rank: (n: number) => `추천 ${n}위`,
    whyTitle: "AI 추천 이유",
    checkin: "체크인",
    checkout: "체크아웃",
    adults: "인원",
    preferences: "선호 조건",
  },
  en: {
    eyebrow: "Stay",
    title: "Hotel Recommendation",
    description: "Describe what you're looking for in natural language. AI will find the best match.",
    placeholder:
      "e.g. I'm visiting Paris July 10–15, looking for a hotel near the Eiffel Tower, close to metro, with breakfast. Two adults.",
    search: "Get AI Recommendations",
    loading: "AI is analyzing your request...",
    noResults: "No hotels matched your criteria. Try rephrasing your request.",
    parsedTitle: "What AI understood",
    book: "Booking.com →",
    viewRooms: "View rooms",
    hideRooms: "Hide",
    breakfast: "Breakfast",
    freeCancellation: "Free cancel",
    payLater: "Pay later",
    perNight: "/ night",
    reviewsCount: (n: number) => `${n.toLocaleString()} reviews`,
    rank: (n: number) => `#${n} Pick`,
    whyTitle: "Why AI recommends this",
    checkin: "Check-in",
    checkout: "Check-out",
    adults: "Guests",
    preferences: "Preferences",
  },
} as const;

function fmt(price: number | null, _currency?: string) {
  if (price == null) return "—";
  return price.toLocaleString("ko-KR") + "원";
}

const stars = (n: number | null) => (n && n > 0 ? "★".repeat(Math.min(n, 5)) : null);

export function AccommodationSearchPage() {
  const { language } = useLanguage();
  const copy = COPY[language];

  const [query, setQuery] = useState("");
  const [hotels, setHotels] = useState<HotelRecommendation[]>([]);
  const [parsedParams, setParsedParams] = useState<{
    destination?: string; checkin?: string; checkout?: string;
    adults?: number; currency?: string; preferences?: string[];
  } | null>(null);
  const [expandedId, setExpandedId] = useState<string | number | null>(null);
  const [rooms, setRooms] = useState<Record<string, Room[]>>({});
  const [agentSummary, setAgentSummary] = useState<string | null>(null);
  const [rankingSummary, setRankingSummary] = useState<Record<string, unknown> | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [roomLoading, setRoomLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const currency = parsedParams?.currency ?? "KRW";

  async function handleSearch(e: FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setHotels([]);
    setParsedParams(null);
    setExpandedId(null);
    setRooms({});
    try {
      const result = await recommendHotels(query);
      setHotels(result.hotels);
      setParsedParams(result.parsedParams);
      setAgentSummary(result.agent_summary ?? null);
      setRankingSummary(result.ranking_summary ?? null);
      setWarnings(result.warnings ?? []);
      if (result.hotels.length === 0) setError(copy.noResults);
    } catch (err) {
      setError(err instanceof Error ? err.message : "추천 요청에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }

  async function toggleRooms(hotel: HotelRecommendation) {
    const key = String(hotel.hotelId);
    if (expandedId === hotel.hotelId) { setExpandedId(null); return; }
    setExpandedId(hotel.hotelId);
    if (rooms[key]) return;
    setRoomLoading(true);
    try {
      const result = await fetchRooms(hotel.hotelId, {
        checkin: parsedParams?.checkin ?? "",
        checkout: parsedParams?.checkout ?? "",
        adults: parsedParams?.adults,
        currency,
      });
      setRooms((prev) => ({ ...prev, [key]: result.rooms }));
    } catch {
      setRooms((prev) => ({ ...prev, [key]: [] }));
    } finally {
      setRoomLoading(false);
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

        <AgentSummaryCard
          title={language === "en" ? "Hotel agent review" : "숙소 Agent 검토"}
          summary={agentSummary}
          constraints={parsedParams as Record<string, unknown> | null}
          repairSummary={rankingSummary}
          warnings={warnings}
        />

        {/* ── AI가 이해한 조건 요약 ── */}
        {parsedParams && !loading && (
          <div className="parsed-params-card">
            <span className="parsed-params-title">{copy.parsedTitle}</span>
            <div className="parsed-params-tags">
              {parsedParams.checkin && (
                <span className="param-tag">{copy.checkin}: {parsedParams.checkin}</span>
              )}
              {parsedParams.checkout && (
                <span className="param-tag">{copy.checkout}: {parsedParams.checkout}</span>
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

        {/* ── 호텔 결과 ── */}
        {hotels.length > 0 && (
          <ul className="results-panel hotel-list">
            {hotels.map((h) => {
              const key = String(h.hotelId);
              const isExpanded = expandedId === h.hotelId;
              const hotelRooms = rooms[key];

              return (
                <li key={key} className="hotel-card">
                  <div className="hotel-card-main">
                    <div className="hotel-photo-wrap">
                      {h.photoUrl ? (
                        <img src={h.photoUrl} alt={h.name ?? ""} className="hotel-photo" loading="lazy" />
                      ) : (
                        <div className="hotel-photo-placeholder">🏨</div>
                      )}
                    </div>

                    <div className="hotel-info">
                      <div className="hotel-name-row">
                        <span className="ai-rank-badge">{copy.rank(h.rank)}</span>
                        <span className="hotel-name">{h.name}</span>
                        {stars(h.stars) && <span className="hotel-stars">{stars(h.stars)}</span>}
                      </div>

                      {h.reviewScore != null && (
                        <div className="hotel-review">
                          <span className="review-score-badge">{h.reviewScore}</span>
                          {h.reviewScoreWord && <span className="review-word">{h.reviewScoreWord}</span>}
                          {h.reviewCount != null && (
                            <span className="review-count">{copy.reviewsCount(h.reviewCount)}</span>
                          )}
                        </div>
                      )}

                      <div className="hotel-price-row">
                        <span className="hotel-price">{fmt(h.price, h.currency || currency)}</span>
                        <span className="hotel-price-unit">{copy.perNight}</span>
                      </div>

                      {h.reason && (
                        <div className="ai-reason-box">
                          <span className="ai-reason-label">{copy.whyTitle}</span>
                          <p className="ai-reason-text">{h.reason}</p>
                        </div>
                      )}

                      <div className="hotel-actions">
                        <button
                          type="button"
                          className="secondary-button small"
                          onClick={() => toggleRooms(h)}
                          disabled={roomLoading && !hotelRooms}
                        >
                          {isExpanded ? copy.hideRooms : copy.viewRooms}
                        </button>
                        {h.deepLink && (
                          <a href={h.deepLink} target="_blank" rel="noopener noreferrer" className="book-link">
                            {copy.book}
                          </a>
                        )}
                      </div>
                    </div>
                  </div>

                  {isExpanded && hotelRooms && hotelRooms.length > 0 && (
                    <ul className="room-list">
                      {hotelRooms.map((r) => (
                        <li key={r.roomId} className="room-item">
                          <span className="room-name">{r.roomName}</span>
                          <span className="room-price">{fmt(r.price, r.currency || currency)}{copy.perNight}</span>
                          <div className="room-tags">
                            {r.breakfastIncluded && <span className="room-tag">{copy.breakfast}</span>}
                            {r.freeCancellation && <span className="room-tag">{copy.freeCancellation}</span>}
                            {r.payLater && <span className="room-tag">{copy.payLater}</span>}
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}

                  {isExpanded && hotelRooms?.length === 0 && (
                    <p style={{ padding: "12px 18px", color: "var(--muted)", fontSize: "0.86rem" }}>
                      객실 정보를 불러오지 못했습니다.
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}

      </div>
    </PageContainer>
  );
}
