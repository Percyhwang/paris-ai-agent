import { useLanguage } from "../../store/LanguageContext";
import { formatDate } from "../../utils/format";
import type { WeatherDay } from "../../types";

export function WeatherCard({ day }: { day: WeatherDay }) {
  const { language } = useLanguage();
  const precipitationLabel = language === "en" ? "Rain" : "강수";

  return (
    <article className="weather-card">
      <div className="weather-icon">{day.icon}</div>
      <div>
        <span>{formatDate(day.date, language)}</span>
        <h3>{day.condition}</h3>
        <p>
          {day.temp_min_c}°C / {day.temp_max_c}°C
        </p>
      </div>
      <div className="rain-chip">
        {precipitationLabel} {day.precipitation_chance}%
      </div>
      <p className="weather-tip">{day.travel_tip}</p>
    </article>
  );
}
