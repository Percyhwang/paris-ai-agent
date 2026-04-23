import type { ItineraryDay } from "../../types";

const timeSlotLabels = {
  morning: "오전",
  lunch: "점심",
  afternoon: "오후",
  evening: "저녁",
};

export function Timeline({ day }: { day: ItineraryDay }) {
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
              {item.place.category ? <span>{item.place.category}</span> : null}
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}
