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

type RouteOverlayPoint = {
  x: number;
  y: number;
  label: string;
};

function formatCoordinates(place: MapPlace): string | null {
  if (!place.coordinates) {
    return null;
  }
  return `${place.coordinates.lat},${place.coordinates.lng}`;
}

function isCoordinateText(value: string | null): value is string {
  return Boolean(value);
}

function routePlaceKeys(place: MapPlace): string[] {
  const coordinates = place.coordinates;
  const name = place.name.trim().toLowerCase();
  const keys = name ? [`name:${name}`] : [];
  if (!coordinates) {
    return keys;
  }
  keys.push(`coord:${coordinates.lat.toFixed(5)},${coordinates.lng.toFixed(5)}`);
  return keys;
}

function uniqueRoutePlaces(places: MapPlace[]): MapPlace[] {
  const seen = new Set<string>();
  return places.filter((place) => {
    if (!place.coordinates) {
      return false;
    }
    const keys = routePlaceKeys(place);
    if (keys.some((key) => seen.has(key))) {
      return false;
    }
    keys.forEach((key) => seen.add(key));
    return true;
  });
}

function buildEmbedUrl(routePlaces: MapPlace[], center: Coordinates): string {
  if (routePlaces.length < 2) {
    return `https://maps.google.com/maps?q=${center.lat},${center.lng}&z=13&output=embed`;
  }

  const origin = formatCoordinates(routePlaces[0]);
  const stops = routePlaces.slice(1).map(formatCoordinates).filter(isCoordinateText);
  if (!origin || !stops.length) {
    return `https://maps.google.com/maps?q=${center.lat},${center.lng}&z=13&output=embed`;
  }

  const destinationPath = stops.map((stop) => encodeURIComponent(stop)).join("+to:");
  return `https://maps.google.com/maps?f=d&source=s_d&saddr=${encodeURIComponent(origin)}&daddr=${destinationPath}&dirflg=r&output=embed`;
}

function buildOpenRouteUrl(routePlaces: MapPlace[], center: Coordinates): string {
  const routePath = routePlaces.map(formatCoordinates).filter(isCoordinateText).join("/");
  if (routePlaces.length < 2 || !routePath) {
    return `https://www.google.com/maps/search/?api=1&query=${center.lat},${center.lng}`;
  }
  return `https://www.google.com/maps/dir/${routePath}/?travelmode=transit`;
}

function buildOverlayPoints(routePlaces: MapPlace[]): RouteOverlayPoint[] {
  const coordinatePlaces = routePlaces.filter((place) => place.coordinates);
  if (coordinatePlaces.length < 2) {
    return [];
  }

  const latitudes = coordinatePlaces.map((place) => place.coordinates?.lat ?? 0);
  const longitudes = coordinatePlaces.map((place) => place.coordinates?.lng ?? 0);
  const minLat = Math.min(...latitudes);
  const maxLat = Math.max(...latitudes);
  const minLng = Math.min(...longitudes);
  const maxLng = Math.max(...longitudes);
  const latSpan = Math.max(maxLat - minLat, 0.01);
  const lngSpan = Math.max(maxLng - minLng, 0.01);
  const padding = 14;
  const drawable = 100 - padding * 2;

  return coordinatePlaces.map((place, index) => {
    const coordinates = place.coordinates as Coordinates;
    return {
      x: padding + ((coordinates.lng - minLng) / lngSpan) * drawable,
      y: padding + ((maxLat - coordinates.lat) / latSpan) * drawable,
      label: String(index + 1),
    };
  });
}

export function GoogleMapViewer({ places, compact = false }: GoogleMapViewerProps) {
  const { language } = useLanguage();
  const routePlaces = uniqueRoutePlaces(places);
  const firstPlace = routePlaces[0];
  const center = firstPlace?.coordinates ?? { lat: 48.8566, lng: 2.3522 };
  const mapUrl = buildEmbedUrl(routePlaces, center);
  const openRouteUrl = buildOpenRouteUrl(routePlaces, center);
  const overlayPoints = buildOverlayPoints(routePlaces);
  const overlayPolyline = overlayPoints.map((point) => `${point.x},${point.y}`).join(" ");

  const copy =
    language === "en"
      ? {
          title: "Paris Google Maps preview",
          routeTitle: "Day Route",
          empty: "Select a place to show the route on the map.",
          open: "Open in Google Maps",
        }
      : {
          title: "파리 Google 지도 미리보기",
          routeTitle: "일차별 동선",
          empty: "장소를 선택하면 지도에 동선이 표시됩니다.",
          open: "Google Maps로 보기",
        };

  return (
    <section className={`map-viewer ${compact ? "compact" : ""}`}>
      <div className="map-canvas">
        <iframe title={copy.title} src={mapUrl} loading="lazy" referrerPolicy="no-referrer-when-downgrade" />
        {overlayPoints.length >= 2 ? (
          <svg className="map-route-overlay" viewBox="0 0 100 100" aria-hidden="true" preserveAspectRatio="none">
            <polyline points={overlayPolyline} />
            {overlayPoints.map((point, index) => (
              <g key={`${point.label}-${index}`}>
                <circle cx={point.x} cy={point.y} r="3.2" />
                <text x={point.x} y={point.y + 0.8}>
                  {point.label}
                </text>
              </g>
            ))}
          </svg>
        ) : null}
      </div>
      {!compact ? (
        <div className="map-route-list">
          <div className="map-route-head">
            <strong>{copy.routeTitle}</strong>
            <a href={openRouteUrl} target="_blank" rel="noreferrer">
              {copy.open}
            </a>
          </div>
          {routePlaces.length ? (
            routePlaces.map((place, index) => (
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
