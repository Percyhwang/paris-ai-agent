import { FormEvent, useState } from "react";
import { PageContainer } from "../components/common/PageContainer";
import { useLanguage } from "../store/LanguageContext";
import { fetchRooms, searchHotels, type Hotel, type Room } from "../services/hotelService";

const COPY = {
  ko: {
    eyebrow: "Stay",
    title: "숙소 검색",
    description: "Booking.com API로 실시간 숙소를 조회합니다.",
    destination: "도시",
    checkIn: "체크인",
    checkOut: "체크아웃",
    guests: "인원",
    search: "숙소 검색",
    loading: "검색 중...",
    noResults: "검색 결과가 없습니다.",
    book: "Booking.com →",
    viewRooms: "객실 보기",
    hideRooms: "접기",
    breakfast: "조식 포함",
    freeCancellation: "무료 취소",
    payLater: "나중에 결제",
    perNight: "/ 박",
    reviewsCount: (n: number) => `리뷰 ${n.toLocaleString()}개`,
  },
  en: {
    eyebrow: "Stay",
    title: "Accommodation Search",
    description: "Search real-time hotels via Booking.com API.",
    destination: "City",
    checkIn: "Check-in",
    checkOut: "Check-out",
    guests: "Guests",
    search: "Search Hotels",
    loading: "Searching...",
    noResults: "No results found.",
    book: "Booking.com →",
    viewRooms: "View rooms",
    hideRooms: "Hide",
    breakfast: "Breakfast",
    freeCancellation: "Free cancel",
    payLater: "Pay later",
    perNight: "/ night",
    reviewsCount: (n: number) => `${n.toLocaleString()} reviews`,
  },
} as const;

const CURRENCY_SYMBOLS: Record<string, string> = {
  EUR: "€",
  USD: "$",
  KRW: "₩",
};

function fmt(price: number | null, currency: string) {
  if (price == null) return "—";
  const symbol = CURRENCY_SYMBOLS[currency] ?? currency + " ";
  if (currency === "KRW") return price.toLocaleString("ko-KR") + "원";
  return symbol + price.toLocaleString("en-US");
}

const stars = (n: number | null) => (n && n > 0 ? "★".repeat(Math.min(n, 5)) : null);

const CURRENCIES = ["EUR", "USD", "KRW"];

export function AccommodationSearchPage() {
  const { language } = useLanguage();
  const copy = COPY[language];

  const [destination, setDestination] = useState("Paris");
  const [checkin, setCheckin] = useState("");
  const [checkout, setCheckout] = useState("");
  const [adults, setAdults] = useState(2);
  const [currency, setCurrency] = useState("EUR");

  const [hotels, setHotels] = useState<Hotel[]>([]);
  const [expandedId, setExpandedId] = useState<string | number | null>(null);
  const [rooms, setRooms] = useState<Record<string, Room[]>>({});
  const [loading, setLoading] = useState(false);
  const [roomLoading, setRoomLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setExpandedId(null);
    setRooms({});
    try {
      const result = await searchHotels({ destination, checkin, checkout, adults, currency });
      setHotels(result.hotels);
      if (result.hotels.length === 0) setError(copy.noResults);
    } catch (err) {
      setError(err instanceof Error ? err.message : "검색에 실패했습니다.");
      setHotels([]);
    } finally {
      setLoading(false);
    }
  }

  async function toggleRooms(hotel: Hotel) {
    const key = String(hotel.hotelId);
    if (expandedId === hotel.hotelId) {
      setExpandedId(null);
      return;
    }
    setExpandedId(hotel.hotelId);
    if (rooms[key]) return;
    setRoomLoading(true);
    try {
      const result = await fetchRooms(hotel.hotelId, { checkin, checkout, adults, currency });
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

        {/* ── 검색 폼 ── */}
        <form className="booking-search-panel stacked-form" onSubmit={handleSearch}>
          <div className="form-row">
            <label>
              {copy.destination}
              <input value={destination} onChange={(e) => setDestination(e.target.value)} placeholder="Paris" required />
            </label>
            <div className="form-row" style={{ gap: 6 }}>
              <label style={{ minWidth: 0 }}>
                {copy.guests}
                <input type="number" min="1" max="9" value={adults} onChange={(e) => setAdults(Number(e.target.value))} />
              </label>
              <label style={{ minWidth: 0 }}>
                통화
                <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
                  {CURRENCIES.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </label>
            </div>
          </div>
          <div className="form-row">
            <label>
              {copy.checkIn}
              <input type="date" value={checkin} onChange={(e) => setCheckin(e.target.value)} required />
            </label>
            <label>
              {copy.checkOut}
              <input type="date" value={checkout} onChange={(e) => setCheckout(e.target.value)} required />
            </label>
          </div>
          <div className="booking-search-actions">
            <button type="submit" className="primary-button" disabled={loading}>
              {loading ? copy.loading : copy.search}
            </button>
          </div>
        </form>

        {error && <p className="error-message">{error}</p>}

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

                    {/* 사진 */}
                    <div className="hotel-photo-wrap">
                      {h.photoUrl ? (
                        <img src={h.photoUrl} alt={h.name ?? ""} className="hotel-photo" loading="lazy" />
                      ) : (
                        <div className="hotel-photo-placeholder">🏨</div>
                      )}
                    </div>

                    {/* 정보 */}
                    <div className="hotel-info">
                      <div className="hotel-name-row">
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

                  {/* 객실 목록 */}
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
