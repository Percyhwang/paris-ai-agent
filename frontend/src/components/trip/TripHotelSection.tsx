import { FormEvent, useState } from "react";
import { useLanguage } from "../../store/LanguageContext";
import { recommendHotels, fetchRooms, type HotelRecommendation, type Room } from "../../services/hotelService";
import type { Trip } from "../../types";

const COPY = {
  ko: {
    sectionTitle: "이 여행에 맞는 숙소",
    sectionDesc: "일정 정보를 바탕으로 AI가 쿼리를 미리 작성했어요. 수정 후 추천받으세요.",
    search: "AI 추천받기",
    loading: "AI가 분석 중입니다...",
    noResults: "조건에 맞는 숙소를 찾지 못했습니다.",
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
    sectionTitle: "Hotels for this trip",
    sectionDesc: "AI pre-filled the query from your itinerary. Edit and search.",
    search: "Get AI Recommendations",
    loading: "AI is analyzing...",
    noResults: "No hotels matched your criteria.",
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

function fmt(price: number | null) {
  if (price == null) return "—";
  return price.toLocaleString("ko-KR") + "원";
}

const stars = (n: number | null) => (n && n > 0 ? "★".repeat(Math.min(n, 5)) : null);

const CORE_STAY_EXCLUDED_CATEGORIES = new Set([
  "free_time",
  "rest",
  "buffer",
  "meal_placeholder",
]);

const MEAL_CATEGORIES = new Set([
  "restaurant",
  "cafe",
  "bakery",
  "bistro",
  "brasserie",
  "wine_bar",
  "bar",
]);

function buildStayPlaceList(trip: Trip) {
  const seen = new Set<string>();
  const corePlaces: string[] = [];
  const fallbackPlaces: string[] = [];

  for (const day of trip.itinerary_days) {
    for (const item of day.items) {
      const category = item.place.category?.toLowerCase() ?? "";
      const name = item.place.name?.trim();
      if (!name) continue;
      if (item.itemKind === "gap" || item.nearbyMealNeeded) continue;
      if (CORE_STAY_EXCLUDED_CATEGORIES.has(category)) continue;
      if (seen.has(name)) continue;
      seen.add(name);
      if (!MEAL_CATEGORIES.has(category)) {
        corePlaces.push(name);
      } else {
        fallbackPlaces.push(name);
      }
    }
  }

  return [...corePlaces, ...fallbackPlaces].slice(0, 4);
}

function buildQuery(trip: Trip): string {
  const parts: string[] = [];

  if (trip.start_date) parts.push(`체크인 ${trip.start_date}`);
  if (trip.end_date) parts.push(`체크아웃 ${trip.end_date}`);
  parts.push("파리 호텔");

  const places = buildStayPlaceList(trip);
  if (places.length) parts.push(`방문 예정: ${places.join(", ")}`);

  if (trip.style_tags.length) parts.push(`여행 스타일: ${trip.style_tags.join(", ")}`);

  parts.push("성인 2명");
  return parts.join(". ") + ".";
}

interface Props {
  trip: Trip;
}

export function TripHotelSection({ trip }: Props) {
  const { language } = useLanguage();
  const copy = COPY[language];

  const [query, setQuery] = useState(() => buildQuery(trip));
  const [hotels, setHotels] = useState<HotelRecommendation[]>([]);
  const [parsedParams, setParsedParams] = useState<{
    checkin?: string; checkout?: string; adults?: number;
    currency?: string; preferences?: string[];
  } | null>(null);
  const [expandedId, setExpandedId] = useState<string | number | null>(null);
  const [rooms, setRooms] = useState<Record<string, Room[]>>({});
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
    <section className="trip-hotel-section">
      <div className="trip-hotel-header">
        <h3 className="trip-hotel-title">{copy.sectionTitle}</h3>
        <p className="trip-hotel-desc">{copy.sectionDesc}</p>
      </div>

      <form className="nl-search-panel" onSubmit={handleSearch}>
        <textarea
          className="nl-search-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          rows={3}
        />
        <div className="booking-search-actions">
          <button type="submit" className="primary-button" disabled={loading}>
            {loading ? copy.loading : copy.search}
          </button>
        </div>
      </form>

      {error && <p className="error-message">{error}</p>}

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
                      <span className="hotel-price">{fmt(h.price)}</span>
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
                        <span className="room-price">{fmt(r.price)}{copy.perNight}</span>
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
    </section>
  );
}
