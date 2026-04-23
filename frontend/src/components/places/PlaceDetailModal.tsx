import type { Place } from "../../types";
import { GoogleMapViewer } from "../itinerary/GoogleMapViewer";

type PlaceDetailModalProps = {
  place: Place | null;
  onClose: () => void;
  onAddToPlan: (place: Place) => void;
};

export function PlaceDetailModal({ place, onClose, onAddToPlan }: PlaceDetailModalProps) {
  if (!place) return null;

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section className="place-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <button type="button" className="modal-close" onClick={onClose} aria-label="닫기">
          ×
        </button>
        <img className="modal-hero" src={place.image_url} alt={place.name} />
        <div className="modal-content">
          <span className="category-pill">{place.category}</span>
          <h2>{place.name}</h2>
          <p>{place.full_description}</p>
          <div className="detail-grid">
            <div>
              <h4>역사</h4>
              <p>{place.history}</p>
            </div>
            <div>
              <h4>방문 팁</h4>
              <ul>
                {place.photo_spot_tips.map((tip) => (
                  <li key={tip}>{tip}</li>
                ))}
              </ul>
            </div>
          </div>
          <div className="info-strip">
            <span>소요 시간 {place.estimated_visit_duration}</span>
            <span>{place.admission_fee ?? "입장료 정보 없음"}</span>
            <span>{place.location}</span>
          </div>
          <GoogleMapViewer places={[{ name: place.name, coordinates: place.coordinates }]} compact />
          <button type="button" className="primary-button" onClick={() => onAddToPlan(place)}>
            내 여행 계획에 추가
          </button>
        </div>
      </section>
    </div>
  );
}
