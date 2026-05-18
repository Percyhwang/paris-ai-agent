import type { Place } from "../../types";
import { useLanguage } from "../../store/LanguageContext";
import { getPlaceCategoryLabel } from "../../utils/placeLabels";
import { GoogleMapViewer } from "../itinerary/GoogleMapViewer";

type PlaceDetailModalProps = {
  place: Place | null;
  onClose: () => void;
  onAddToPlan: (place: Place) => void;
};

const MODAL_COPY = {
  ko: {
    close: "닫기",
    about: "장소 소개",
    tips: "방문 팁",
    duration: "소요 시간",
    admissionFallback: "최신 입장 정보는 현장 또는 공식 사이트에서 확인해 주세요",
    addToPlan: "내 여행 계획에 추가",
    emptyHistory: "파리 일정 흐름에 자연스럽게 넣기 좋은 장소입니다.",
    emptyTip: "방문 전 최근 사진과 혼잡도를 확인하면 더 좋은 시간대를 고르기 쉽습니다.",
  },
  en: {
    close: "Close",
    about: "About This Spot",
    tips: "Visit Tips",
    duration: "Suggested Visit",
    admissionFallback: "Check the venue or official site for current admission details",
    addToPlan: "Add to My Trip Plan",
    emptyHistory: "This is a useful Paris stop to weave into a travel route.",
    emptyTip: "Check recent photos and crowd levels before visiting.",
  },
} as const;

export function PlaceDetailModal({ place, onClose, onAddToPlan }: PlaceDetailModalProps) {
  const { language } = useLanguage();
  const copy = MODAL_COPY[language];

  if (!place) return null;

  const tips = place.photo_spot_tips?.length ? place.photo_spot_tips : [copy.emptyTip];
  const imageUrl = place.image_url || "/images/paris-default-hero.jpeg";

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section className="place-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <button type="button" className="modal-close" onClick={onClose} aria-label={copy.close}>
          ×
        </button>
        <div className="modal-image-frame">
          <img
            className="modal-hero"
            src={imageUrl}
            alt={place.name}
            onError={(event) => {
              event.currentTarget.src = "/images/paris-default-hero.jpeg";
            }}
          />
        </div>
        <div className="modal-content">
          <span className="category-pill">{getPlaceCategoryLabel(place.category, language)}</span>
          <h2>{place.name}</h2>
          <p>{place.full_description}</p>
          <div className="detail-grid">
            <div>
              <h4>{copy.about}</h4>
              <p>{place.history || copy.emptyHistory}</p>
            </div>
            <div>
              <h4>{copy.tips}</h4>
              <ul>
                {tips.map((tip) => (
                  <li key={tip}>{tip}</li>
                ))}
              </ul>
            </div>
          </div>
          <div className="info-strip">
            <span>
              {copy.duration} {place.estimated_visit_duration}
            </span>
            <span>{place.admission_fee ?? copy.admissionFallback}</span>
            <span>{place.location}</span>
          </div>
          <GoogleMapViewer places={[{ name: place.name, coordinates: place.coordinates }]} compact />
          <button type="button" className="primary-button" onClick={() => onAddToPlan(place)}>
            {copy.addToPlan}
          </button>
        </div>
      </section>
    </div>
  );
}
