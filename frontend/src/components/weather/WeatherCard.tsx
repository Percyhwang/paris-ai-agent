import { formatDate } from "../../utils/format";
import type { WeatherDay } from "../../types";

export function WeatherCard({ day }: { day: WeatherDay }) {
  return (
    <article className="weather-card">
      <div className="weather-icon">{day.icon}</div>
      <div>
        <span>{formatDate(day.date)}</span>
        <h3>{day.condition}</h3>
        <p>
          {day.temp_min_c}°C / {day.temp_max_c}°C
        </p>
      </div>
      <div className="rain-chip">강수 {day.precipitation_chance}%</div>
      <p className="weather-tip">{day.travel_tip}</p>
    </article>
  );
}
