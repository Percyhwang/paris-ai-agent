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
  const firstPlace = places.find((place) => place.coordinates);
  const center = firstPlace?.coordinates ?? { lat: 48.8566, lng: 2.3522 };
  const mapUrl = `https://www.google.com/maps?q=${center.lat},${center.lng}&z=13&output=embed`;

  return (
    <section className={`map-viewer ${compact ? "compact" : ""}`}>
      <iframe title="Google Maps Paris route preview" src={mapUrl} loading="lazy" referrerPolicy="no-referrer-when-downgrade" />
      {!compact ? (
        <div className="map-route-list">
          <strong>동선 포인트</strong>
          {places.length ? (
            places.map((place, index) => (
              <span key={`${place.name}-${index}`}>
                {index + 1}. {place.name}
              </span>
            ))
          ) : (
            <span>장소를 선택하면 지도 동선이 표시됩니다.</span>
          )}
        </div>
      ) : null}
    </section>
  );
}
