import { useEffect, useState } from "react";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingState } from "../components/common/LoadingState";
import { PageContainer } from "../components/common/PageContainer";
import { PlaceCard } from "../components/places/PlaceCard";
import { PlaceDetailModal } from "../components/places/PlaceDetailModal";
import { placeService } from "../services/placeService";
import type { Place } from "../types";

const categories = ["all", "landmark", "museum", "cathedral", "park", "neighborhood"];

export function PlacesPage() {
  const [places, setPlaces] = useState<Place[]>([]);
  const [selectedPlace, setSelectedPlace] = useState<Place | null>(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const [isLoading, setIsLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(async () => {
      setIsLoading(true);
      try {
        const data = await placeService.listPlaces({ search, category, sort: "popular" });
        setPlaces(data);
      } finally {
        setIsLoading(false);
      }
    }, 200);
    return () => window.clearTimeout(timer);
  }, [search, category]);

  function handleAddToPlan(place: Place) {
    localStorage.setItem("pendingPlaceForTrip", JSON.stringify(place));
    setMessage(`${place.name}을(를) 다음 여행 계획에 추가할 준비가 되었어요.`);
    setSelectedPlace(null);
  }

  return (
    <PageContainer
      eyebrow="Explore Paris"
      title="파리 관광지"
      description="대표 랜드마크와 감성 산책 코스를 검색하고 여행 계획에 담아보세요."
    >
      <div className="toolbar">
        <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="관광지, 태그, 분위기 검색" />
        <div className="chip-row">
          {categories.map((item) => (
            <button key={item} type="button" className={category === item ? "chip active" : "chip"} onClick={() => setCategory(item)}>
              {item === "all" ? "전체" : item}
            </button>
          ))}
        </div>
      </div>
      {message ? <p className="success-note">{message}</p> : null}
      {isLoading ? <LoadingState /> : null}
      {!isLoading && !places.length ? (
        <EmptyState title="검색 결과가 없습니다" description="다른 키워드나 카테고리로 다시 탐색해보세요." />
      ) : null}
      <div className="place-grid">
        {places.map((place) => (
          <PlaceCard key={place.id ?? place.slug} place={place} onSelect={setSelectedPlace} />
        ))}
      </div>
      <PlaceDetailModal place={selectedPlace} onClose={() => setSelectedPlace(null)} onAddToPlan={handleAddToPlan} />
    </PageContainer>
  );
}
