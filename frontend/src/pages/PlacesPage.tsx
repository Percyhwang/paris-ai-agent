import { useEffect, useState } from "react";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingState } from "../components/common/LoadingState";
import { PageContainer } from "../components/common/PageContainer";
import { PlaceCard } from "../components/places/PlaceCard";
import { PlaceDetailModal } from "../components/places/PlaceDetailModal";
import { placeService } from "../services/placeService";
import { useLanguage } from "../store/LanguageContext";
import type { Place } from "../types";
import { getPlaceCategoryLabel } from "../utils/placeLabels";

const categories = ["all", "landmark", "museum", "cathedral", "park", "neighborhood"] as const;

const PLACES_COPY = {
  ko: {
    eyebrow: "파리 명소 가이드",
    title: "파리 스팟",
    description: "랜드마크부터 박물관, 공원과 감성적인 동네까지 원하는 분위기의 파리 명소를 찾아보세요.",
    searchPlaceholder: "관광지 이름, 태그, 분위기를 검색해 보세요",
    loading: "파리 스팟을 불러오고 있습니다",
    loadError: "파리 스팟을 불러오지 못했습니다.",
    emptyTitle: "검색 결과가 없습니다",
    emptyDescription: "다른 검색어나 카테고리로 다시 찾아보세요.",
    addMessage: (name: string) => `${name} 정보를 다음 여행 계획에 담을 준비를 마쳤어요.`,
  },
  en: {
    eyebrow: "Paris Spot Guide",
    title: "Paris Spots",
    description: "Explore Paris landmarks, museums, parks, and neighborhoods without changing the current UI feel.",
    searchPlaceholder: "Search by place name, vibe, or tag",
    loading: "Loading Paris spots",
    loadError: "Could not load Paris spots.",
    emptyTitle: "No places matched your search",
    emptyDescription: "Try a different keyword or switch categories.",
    addMessage: (name: string) => `${name} is ready to be added to your next trip plan.`,
  },
} as const;

function getPlacesErrorMessage(error: unknown, language: "ko" | "en", fallback: string) {
  if (!(error instanceof Error)) return fallback;
  if (error.message.includes("IP restriction")) {
    return language === "en"
      ? error.message
      : "Google Places API 키의 IP 제한 때문에 현재 백엔드 서버 요청이 차단되었습니다. Google Cloud 콘솔에서 이 서버 IP를 허용하거나 백엔드용 Places API 키를 사용해 주세요.";
  }
  return error.message;
}

export function PlacesPage() {
  const { language } = useLanguage();
  const copy = PLACES_COPY[language];
  const [places, setPlaces] = useState<Place[]>([]);
  const [selectedPlace, setSelectedPlace] = useState<Place | null>(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(async () => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await placeService.listPlaces({ search, category, sort: "popular" });
        setPlaces(data);
      } catch (err) {
        setPlaces([]);
        setError(getPlacesErrorMessage(err, language, copy.loadError));
      } finally {
        setIsLoading(false);
      }
    }, 200);
    return () => window.clearTimeout(timer);
  }, [search, category, copy.loadError]);

  function handleAddToPlan(place: Place) {
    localStorage.setItem("pendingPlaceForTrip", JSON.stringify(place));
    setMessage(copy.addMessage(place.name));
    setSelectedPlace(null);
  }

  return (
    <PageContainer eyebrow={copy.eyebrow} title={copy.title} description={copy.description} theme="places">
      <div className="toolbar">
        <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={copy.searchPlaceholder} />
        <div className="chip-row">
          {categories.map((item) => (
            <button key={item} type="button" className={category === item ? "chip active" : "chip"} onClick={() => setCategory(item)}>
              {getPlaceCategoryLabel(item, language)}
            </button>
          ))}
        </div>
      </div>
      {message ? <p className="success-note">{message}</p> : null}
      {isLoading ? <LoadingState label={copy.loading} /> : null}
      {error ? <p className="form-error">{error}</p> : null}
      {!isLoading && !error && !places.length ? <EmptyState title={copy.emptyTitle} description={copy.emptyDescription} /> : null}
      <div className="place-grid">
        {places.map((place) => (
          <PlaceCard key={place.id ?? place.slug} place={place} onSelect={setSelectedPlace} />
        ))}
      </div>
      <PlaceDetailModal place={selectedPlace} onClose={() => setSelectedPlace(null)} onAddToPlan={handleAddToPlan} />
    </PageContainer>
  );
}
