import { Fragment } from "react";

import { useLanguage } from "../../store/LanguageContext";
import type { ItineraryDay, ItineraryItem, RouteLeg } from "../../types";
import { getPlaceCategoryLabel } from "../../utils/placeLabels";
import { getTimePeriodKey, TIME_PERIOD_LABELS, type TimePeriodKey } from "../../utils/timePeriods";

const ROUTE_COPY = {
  ko: {
    route: "이동",
    details: "상세 경로",
    fallback: "예상",
    buffer: "여유",
    walk: "도보",
    transit: "대중교통",
    mixed: "이동",
  },
  en: {
    route: "Move",
    details: "Route details",
    fallback: "Estimate",
    buffer: "Buffer",
    walk: "Walk",
    transit: "Transit",
    mixed: "Move",
  },
} as const;

export function Timeline({ day }: { day: ItineraryDay }) {
  const { language } = useLanguage();
  const periodLabels = TIME_PERIOD_LABELS[language];
  const routeCopy = ROUTE_COPY[language];
  const sections = groupItemsByTimePeriod(day.items);

  return (
    <div className="timeline">
      {sections.map((section) => (
        <section className="timeline-section" key={`${section.key}-${section.items[0]?.start_time ?? "empty"}`}>
          <h3 className="timeline-section-header">{periodLabels[section.key]}</h3>
          {section.items.map((item) => (
            <Fragment key={item.id ?? `${item.start_time}-${item.title}`}>
              <article className="timeline-card">
                <div className="timeline-time">
                  <strong>{formatTimeRange(item)}</strong>
                </div>
                <div className="timeline-dot" />
                <div className="timeline-body">
                  <div className="timeline-role-row">
                    <span className="timeline-role-badge">
                      <span aria-hidden="true">{item.role_icon ?? roleIconFallback(item)}</span>
                      {item.role_label ?? getPlaceCategoryLabel(item.place.category ?? "landmark", language)}
                    </span>
                    {item.duration_minutes ? (
                      <span className="timeline-duration">{formatDuration(item.duration_minutes, language)}</span>
                    ) : null}
                  </div>

                  <h3>
                    <a
                      className="place-search-link"
                      href={`https://www.google.com/search?q=${encodeURIComponent(`${item.place.name} Paris`)}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {item.title}
                    </a>
                  </h3>

                  <p className="timeline-reasoning">{item.reasoning ?? item.description}</p>
                  {item.reasoning && item.description ? <p className="timeline-description">{item.description}</p> : null}

                  <div className="info-strip small-strip">
                    <span>{item.place.name}</span>
                    <span>{item.estimated_duration}</span>
                    {item.place.category ? <span>{getPlaceCategoryLabel(item.place.category, language)}</span> : null}
                    {item.place.admission_fee ? <span>{item.place.admission_fee}</span> : null}
                    {item.place.rating ? <span>{item.place.rating.toFixed(1)} / 5</span> : null}
                  </div>
                </div>
              </article>
              {item.route_to_next ? <RouteTransition leg={item.route_to_next} copy={routeCopy} /> : null}
            </Fragment>
          ))}
        </section>
      ))}
    </div>
  );
}

function groupItemsByTimePeriod(items: ItineraryItem[]) {
  return items.reduce<Array<{ key: TimePeriodKey; items: ItineraryItem[] }>>((sections, item) => {
    const key = getTimePeriodKey(item.start_time);
    const lastSection = sections[sections.length - 1];
    if (lastSection?.key === key) {
      lastSection.items.push(item);
    } else {
      sections.push({ key, items: [item] });
    }
    return sections;
  }, []);
}

function RouteTransition({
  leg,
  copy,
}: {
  leg: RouteLeg;
  copy: (typeof ROUTE_COPY)["ko"] | (typeof ROUTE_COPY)["en"];
}) {
  const modeKey = leg.mode === "walk" || leg.mode === "transit" ? leg.mode : "mixed";
  const displaySteps = getDisplaySteps(leg);
  const bufferText = leg.buffer_minutes ? `${copy.buffer} ${leg.buffer_minutes} min` : null;

  return (
    <details className="route-transition">
      <summary>
        <span className="route-transition-icon" aria-hidden="true">
          {routeIcon(modeKey)}
        </span>
        <span className="route-transition-main">{leg.compact_summary ?? leg.summary}</span>
        {bufferText ? <span className="route-transition-buffer">{bufferText}</span> : null}
      </summary>

      <div className="route-transition-panel">
        <div className="route-chip-row">
          <span>{copy[modeKey]}</span>
          {leg.scheduled_duration_text ? <span>{leg.scheduled_duration_text}</span> : null}
          {leg.distance_meters ? <span>{formatDistance(leg.distance_meters)}</span> : null}
          {leg.fallback ? <span>{copy.fallback}</span> : null}
        </div>
        {leg.transit_lines.length ? (
          <div className="route-line-chips">
            {leg.transit_lines.map((line) => (
              <span key={line}>{line}</span>
            ))}
          </div>
        ) : null}
        {displaySteps.length ? (
          <ol className="route-step-list" aria-label={copy.details}>
            {displaySteps.map((step, index) => (
              <li key={`${step.instruction}-${index}`}>
                <span>{step.instruction}</span>
                {step.duration_text ? <small>{step.duration_text}</small> : null}
              </li>
            ))}
          </ol>
        ) : null}
      </div>
    </details>
  );
}

function getDisplaySteps(leg: RouteLeg) {
  if (!leg.steps.length) {
    return [];
  }
  const transitSteps = leg.steps.filter((step) => step.travel_mode === "transit");
  if (!transitSteps.length) {
    return leg.steps.slice(0, 3);
  }
  const selected = [...leg.steps.slice(0, 2), ...transitSteps];
  return selected
    .filter((step, index, steps) => steps.findIndex((candidate) => candidate.instruction === step.instruction) === index)
    .slice(0, 4);
}

function formatTimeRange(item: ItineraryItem) {
  return item.end_time ? `${item.start_time}-${item.end_time}` : item.start_time;
}

function formatDistance(meters: number) {
  return meters >= 1000 ? `${(meters / 1000).toFixed(1)} km` : `${meters} m`;
}

function formatDuration(minutes: number, language: "ko" | "en") {
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  if (language === "en") {
    if (hours && mins) return `${hours}h ${mins}m`;
    if (hours) return `${hours}h`;
    return `${mins}m`;
  }
  if (hours && mins) return `${hours}시간 ${mins}분`;
  if (hours) return `${hours}시간`;
  return `${mins}분`;
}

function routeIcon(mode: string) {
  if (mode === "transit") return "🚇";
  if (mode === "walk") return "🚶";
  return "↳";
}

function roleIconFallback(item: ItineraryItem) {
  const category = item.place.category?.toLowerCase() ?? "";
  if (category.includes("museum") || category.includes("gallery")) return "🖼";
  if (category.includes("cafe")) return "☕";
  if (category.includes("restaurant")) return "🍷";
  if (category.includes("park") || category.includes("garden")) return "🌿";
  return "📍";
}
