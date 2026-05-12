import { useLanguage } from "../../store/LanguageContext";
import type { ItineraryDay } from "../../types";
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

export function Timeline({ day }: { day: ItineraryDay }) {
  const { language } = useLanguage();
  const timeSlotLabels = TIME_SLOT_LABELS[language];

  return (
    <div className="timeline">
      {day.items.map((item) => (
        <article className="timeline-card" key={item.id ?? `${item.start_time}-${item.title}`}>
          <div className="timeline-time">
            <span>{timeSlotLabels[item.time_slot]}</span>
            <strong>{item.start_time}</strong>
          </div>
          <div className="timeline-dot" />
          <div className="timeline-body">
            <h3>{item.title}</h3>
            <p>{item.description}</p>
            <div className="info-strip small-strip">
              <span>{item.place.name}</span>
              <span>{item.estimated_duration}</span>
              {item.place.category ? <span>{getPlaceCategoryLabel(item.place.category, language)}</span> : null}
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}
