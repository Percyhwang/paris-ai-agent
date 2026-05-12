import { useLanguage } from "../../store/LanguageContext";
import type { Coordinates } from "../../types";

type MapPlace = {
  name: string;
  coordinates?: Coordinates | null;
};

type GoogleMapViewerProps = {
  places: MapPlace[];
  compact?: boolean;
};

export function GoogleMapViewer({ places, compact = false }: GoogleMapViewerProps) {
  const { language } = useLanguage();
  const firstPlace = places.find((place) => place.coordinates);
  const center = firstPlace?.coordinates ?? { lat: 48.8566, lng: 2.3522 };
  const mapUrl = `https://www.google.com/maps?q=${center.lat},${center.lng}&z=13&output=embed`;

  const copy =
    language === "en"
      ? {
          title: "Paris Google Maps preview",
          routeTitle: "Route Preview",
          empty: "Select a place to show the route on the map.",
        }
      : {
          title: "파리 구글 지도 미리보기",
          routeTitle: "동선 미리보기",
          empty: "장소를 선택하면 지도에 동선을 표시합니다.",
        };

  return (
    <section className={`map-viewer ${compact ? "compact" : ""}`}>
      <iframe title={copy.title} src={mapUrl} loading="lazy" referrerPolicy="no-referrer-when-downgrade" />
      {!compact ? (
        <div className="map-route-list">
          <strong>{copy.routeTitle}</strong>
          {places.length ? (
            places.map((place, index) => (
              <span key={`${place.name}-${index}`}>
                {index + 1}. {place.name}
              </span>
            ))
          ) : (
            <span>{copy.empty}</span>
          )}
        </div>
      ) : null}
    </section>
  );
}
