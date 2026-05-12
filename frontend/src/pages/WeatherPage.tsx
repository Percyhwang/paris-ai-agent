import { useEffect, useState } from "react";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingState } from "../components/common/LoadingState";
import { PageContainer } from "../components/common/PageContainer";
import { WeatherCard } from "../components/weather/WeatherCard";
import { useLanguage } from "../store/LanguageContext";
import { weatherService } from "../services/weatherService";
import type { WeatherForecast } from "../types";

const WEATHER_COPY = {
  ko: {
    eyebrow: "파리 날씨 가이드",
    title: "파리 날씨",
    description: "일정 선택 전에 주간 예보를 보고, 날씨에 맞는 여행 동선을 가볍게 조정해 보세요.",
    forecastLabel: "예보 기간",
    loading: "파리 날씨를 확인하고 있습니다",
    emptyTitle: "날씨 정보가 없습니다",
    emptyDescription: "잠시 후 다시 시도해 주세요.",
    error: "날씨 정보를 불러오지 못했습니다.",
    days5: "5일",
    days7: "7일",
    days10: "10일",
  },
  en: {
    eyebrow: "Paris Weather Guide",
    title: "Paris Weather",
    description: "Check the weekly forecast before you lock in a route, then fine-tune your plan around the weather.",
    forecastLabel: "Forecast Range",
    loading: "Checking the Paris forecast",
    emptyTitle: "No weather data available",
    emptyDescription: "Please try again in a moment.",
    error: "Could not load the weather forecast.",
    days5: "5 days",
    days7: "7 days",
    days10: "10 days",
  },
} as const;

export function WeatherPage() {
  const { language } = useLanguage();
  const copy = WEATHER_COPY[language];
  const [forecast, setForecast] = useState<WeatherForecast | null>(null);
  const [days, setDays] = useState(7);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function loadWeather() {
      setIsLoading(true);
      setError(null);
      try {
        const data = await weatherService.getParisForecast(days);
        if (mounted) {
          setForecast(data);
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : copy.error);
        }
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    }

    loadWeather();
    return () => {
      mounted = false;
    };
  }, [copy.error, days, language]);

  return (
    <PageContainer
      eyebrow={copy.eyebrow}
      title={copy.title}
      description={copy.description}
      theme="weather"
      action={
        <label className="trip-selector">
          <span>{copy.forecastLabel}</span>
          <select value={days} onChange={(event) => setDays(Number(event.target.value))}>
            <option value={5}>{copy.days5}</option>
            <option value={7}>{copy.days7}</option>
            <option value={10}>{copy.days10}</option>
          </select>
        </label>
      }
    >
      {isLoading ? <LoadingState label={copy.loading} /> : null}
      {error ? <p className="form-error">{error}</p> : null}
      {!isLoading && !forecast ? <EmptyState title={copy.emptyTitle} description={copy.emptyDescription} /> : null}
      {forecast ? (
        <>
          <div className="weather-hero-card">
            <span>
              {forecast.city}, {forecast.country}
            </span>
            <h2>{forecast.days[0]?.condition}</h2>
            <p>{forecast.days[0]?.travel_tip}</p>
          </div>
          <div className="weather-grid">
            {forecast.days.map((day) => (
              <WeatherCard key={day.date} day={day} />
            ))}
          </div>
        </>
      ) : null}
    </PageContainer>
  );
}
