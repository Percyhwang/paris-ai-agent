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
    bufferReason: "여유 이유",
    experience: "기대 포인트",
    editable: "수정 여지",
    effort: "이동 부담",
    nightBadge: "야경",
    raw: "실이동",
    total: "총 이동",
    freeTime: "자유 시간",
    walk: "도보",
    transit: "대중교통",
    mixed: "이동",
  },
  en: {
    route: "Move",
    details: "Route details",
    fallback: "Estimate",
    buffer: "Buffer",
    bufferReason: "Why the buffer",
    experience: "Expected feel",
    editable: "Easy to tweak",
    effort: "Movement load",
    nightBadge: "Night view",
    raw: "Travel",
    total: "Total",
    freeTime: "Free time",
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
              <TimelineItemCard item={item} language={language} routeCopy={routeCopy} />
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

function TimelineItemCard({
  item,
  language,
  routeCopy,
}: {
  item: ItineraryItem;
  language: "ko" | "en";
  routeCopy: (typeof ROUTE_COPY)["ko"] | (typeof ROUTE_COPY)["en"];
}) {
  const primaryReason = item.userPreferenceReason ?? item.reasoning ?? item.description;
  const secondaryDescription = item.description && item.description !== primaryReason ? item.description : null;
  const isHelperItem =
    item.itemKind === "gap" ||
    item.nearbyMealNeeded ||
    item.place.category === "free_time" ||
    item.place.category === "meal_placeholder";

  return (
    <article className={isHelperItem ? "timeline-card timeline-card-gap" : "timeline-card"}>
      <div className="timeline-time">
        <strong>{formatTimeRange(item)}</strong>
      </div>
      <div className="timeline-dot" />
      <div className="timeline-body">
        <div className="timeline-role-row">
          <div className="timeline-role-cluster">
            <span className="timeline-role-badge">
              <span aria-hidden="true">{item.role_icon ?? roleIconFallback(item)}</span>
              {item.role_label ?? getPlaceCategoryLabel(item.place.category ?? "landmark", language)}
            </span>
            {item.isNightViewSpot ? <span className="timeline-night-badge">{routeCopy.nightBadge}</span> : null}
          </div>
          {item.duration_minutes ? <span className="timeline-duration">{formatDuration(item.duration_minutes, language)}</span> : null}
        </div>

        <h3>
          {isHelperItem ? (
            <span>{item.title || routeCopy.freeTime}</span>
          ) : (
            <a
              className="place-search-link"
              href={`https://www.google.com/search?q=${encodeURIComponent(`${item.place.name} Paris`)}`}
              target="_blank"
              rel="noreferrer"
            >
              {item.title}
            </a>
          )}
        </h3>

        {item.slotPurpose ? <p className="timeline-slot-purpose">{item.slotPurpose}</p> : null}
        {primaryReason ? <p className="timeline-reasoning">{primaryReason}</p> : null}
        {item.timeReason ? <p className="timeline-time-reason">{item.timeReason}</p> : null}
        {secondaryDescription ? <p className="timeline-description">{secondaryDescription}</p> : null}
        {item.expectedExperience ? (
          <p className="timeline-experience">
            <strong>{routeCopy.experience}</strong>
            {item.expectedExperience}
          </p>
        ) : null}
        {item.editableReason ? (
          <p className="timeline-editable-note">
            <strong>{routeCopy.editable}</strong>
            {item.editableReason}
          </p>
        ) : null}

        <div className="info-strip small-strip">
          {isHelperItem ? null : <span>{item.place.name}</span>}
          <span>{item.estimated_duration}</span>
          {!isHelperItem && item.place.category ? <span>{getPlaceCategoryLabel(item.place.category, language)}</span> : null}
          {!isHelperItem && item.place.admission_fee ? <span>{item.place.admission_fee}</span> : null}
          {!isHelperItem && item.place.rating ? <span>{item.place.rating.toFixed(1)} / 5</span> : null}
        </div>
      </div>
    </article>
  );
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
  const rawMinutes = leg.rawDurationMinutes ?? (leg.duration_seconds ? Math.max(1, Math.round(leg.duration_seconds / 60)) : null);
  const bufferMinutes = leg.bufferMinutes ?? leg.buffer_minutes ?? null;
  const totalMinutes = leg.totalTransferMinutes ?? (rawMinutes && bufferMinutes !== null ? rawMinutes + bufferMinutes : rawMinutes);
  const effortText = effortLabel(leg.effort_level, copy);
  const transferSummary = transferSummaryText(modeKey, rawMinutes, bufferMinutes, totalMinutes, copy);

  return (
    <details className="route-transition">
      <summary>
        <span className="route-transition-icon" aria-hidden="true">
          {routeIcon(modeKey)}
        </span>
        <span className="route-transition-main">{transferSummary}</span>
        {effortText ? <span className="route-transition-buffer">{copy.effort} {effortText}</span> : null}
      </summary>

      <div className="route-transition-panel">
        <div className="route-chip-row">
          <span>{copy[modeKey]}</span>
          {rawMinutes ? <span>{copy.raw} {formatDuration(rawMinutes, languageFromCopy(copy))}</span> : null}
          {bufferMinutes ? <span>{copy.buffer} {formatDuration(bufferMinutes, languageFromCopy(copy))}</span> : null}
          {totalMinutes ? <span>{copy.total} {formatDuration(totalMinutes, languageFromCopy(copy))}</span> : null}
          {leg.distance_meters ? <span>{formatDistance(leg.distance_meters)}</span> : null}
          {leg.fallback ? <span>{copy.fallback}</span> : null}
        </div>
        {leg.summary && leg.summary !== (leg.comfort_summary ?? leg.compact_summary) ? (
          <p className="route-transition-caption">{leg.summary}</p>
        ) : null}
        {effortText || leg.restBufferReason ? (
          <div className="route-transition-note-list">
            {effortText ? <span>{copy.effort}: {effortText}</span> : null}
            {leg.restBufferReason ? <span>{copy.bufferReason}: {leg.restBufferReason}</span> : null}
          </div>
        ) : null}
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

function transferSummaryText(
  modeKey: "walk" | "transit" | "mixed",
  rawMinutes: number | null,
  bufferMinutes: number | null,
  totalMinutes: number | null,
  copy: (typeof ROUTE_COPY)["ko"] | (typeof ROUTE_COPY)["en"],
) {
  const modeLabel = copy[modeKey];
  const language = languageFromCopy(copy);
  if (!rawMinutes) return modeLabel;
  const rawText = formatDuration(rawMinutes, language);
  if (bufferMinutes && totalMinutes) {
    return `${modeLabel} ${rawText} + ${copy.buffer} ${formatDuration(bufferMinutes, language)} = ${copy.total} ${formatDuration(totalMinutes, language)}`;
  }
  return `${modeLabel} ${rawText}`;
}

function languageFromCopy(copy: (typeof ROUTE_COPY)["ko"] | (typeof ROUTE_COPY)["en"]): "ko" | "en" {
  return copy.route === "Move" ? "en" : "ko";
}

function effortLabel(level: RouteLeg["effort_level"], copy: (typeof ROUTE_COPY)["ko"] | (typeof ROUTE_COPY)["en"]) {
  if (!level) return null;
  if (copy.route === "Move") {
    return level === "low" ? "Low" : level === "high" ? "High" : "Moderate";
  }
  return level === "low" ? "낮음" : level === "high" ? "높음" : "보통";
}

function roleIconFallback(item: ItineraryItem) {
  if (item.itemKind === "gap" || item.place.category === "free_time") return "⏳";
  if (item.nearbyMealNeeded || item.place.category === "meal_placeholder") return "🍽";
  const category = item.place.category?.toLowerCase() ?? "";
  if (category.includes("museum") || category.includes("gallery")) return "🖼";
  if (category.includes("cafe")) return "☕";
  if (category.includes("restaurant")) return "🍷";
  if (category.includes("park") || category.includes("garden")) return "🌿";
  return "📍";
}
