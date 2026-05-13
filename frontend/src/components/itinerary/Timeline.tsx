import { Fragment } from "react";

import { useLanguage } from "../../store/LanguageContext";
import type { ItineraryDay, RouteLeg } from "../../types";
import { getPlaceCategoryLabel } from "../../utils/placeLabels";

const TIME_SLOT_LABELS = {
  ko: {
    morning: "오전",
    lunch: "점심",
    afternoon: "오후",
    evening: "저녁",
  },
  en: {
    morning: "Morning",
    lunch: "Lunch",
    afternoon: "Afternoon",
    evening: "Evening",
  },
} as const;

const ROUTE_COPY = {
  ko: {
    route: "이동",
    fallback: "예상",
    walk: "도보",
    transit: "대중교통",
    mixed: "이동",
  },
  en: {
    route: "Move",
    fallback: "Estimate",
    walk: "Walk",
    transit: "Transit",
    mixed: "Move",
  },
} as const;

export function Timeline({ day }: { day: ItineraryDay }) {
  const { language } = useLanguage();
  const timeSlotLabels = TIME_SLOT_LABELS[language];
  const routeCopy = ROUTE_COPY[language];

  return (
    <div className="timeline">
      {day.items.map((item) => (
        <Fragment key={item.id ?? `${item.start_time}-${item.title}`}>
          <article className="timeline-card">
            <div className="timeline-time">
              <span>{timeSlotLabels[item.time_slot]}</span>
              <strong>{item.start_time}</strong>
            </div>
            <div className="timeline-dot" />
            <div className="timeline-body">
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
              <p>{item.description}</p>
              <div className="info-strip small-strip">
                <span>{item.place.name}</span>
                <span>{item.estimated_duration}</span>
                {item.place.category ? <span>{getPlaceCategoryLabel(item.place.category, language)}</span> : null}
                {item.place.admission_fee ? <span>{item.place.admission_fee}</span> : null}
                {item.place.rating ? <span>{item.place.rating.toFixed(1)} / 5</span> : null}
              </div>
            </div>
          </article>
          {item.route_to_next ? <RouteLegCard leg={item.route_to_next} copy={routeCopy} /> : null}
        </Fragment>
      ))}
    </div>
  );
}

function RouteLegCard({
  leg,
  copy,
}: {
  leg: RouteLeg;
  copy: (typeof ROUTE_COPY)["ko"] | (typeof ROUTE_COPY)["en"];
}) {
  const modeKey = leg.mode === "walk" || leg.mode === "transit" ? leg.mode : "mixed";
  const displaySteps = getDisplaySteps(leg);

  return (
    <article className="route-leg-card">
      <div className="route-leg-time">
        <span>{copy.route}</span>
        <strong>{leg.duration_text}</strong>
      </div>
      <div className="route-leg-line" />
      <div className="route-leg-body">
        <div className="route-leg-head">
          <strong>{leg.summary}</strong>
          <div className="route-chip-row">
            <span>{copy[modeKey]}</span>
            {leg.distance_meters ? <span>{formatDistance(leg.distance_meters)}</span> : null}
            {leg.fallback ? <span>{copy.fallback}</span> : null}
          </div>
        </div>
        {leg.transit_lines.length ? (
          <div className="route-line-chips">
            {leg.transit_lines.map((line) => (
              <span key={line}>{line}</span>
            ))}
          </div>
        ) : null}
        {displaySteps.length ? (
          <ol className="route-step-list">
            {displaySteps.map((step, index) => (
              <li key={`${step.instruction}-${index}`}>
                <span>{step.instruction}</span>
                {step.duration_text ? <small>{step.duration_text}</small> : null}
              </li>
            ))}
          </ol>
        ) : null}
      </div>
    </article>
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

function formatDistance(meters: number) {
  return meters >= 1000 ? `${(meters / 1000).toFixed(1)} km` : `${meters} m`;
}
