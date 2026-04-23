import { useEffect, useState } from "react";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingState } from "../components/common/LoadingState";
import { PageContainer } from "../components/common/PageContainer";
import { WeatherCard } from "../components/weather/WeatherCard";
import { weatherService } from "../services/weatherService";
import type { WeatherForecast } from "../types";

export function WeatherPage() {
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
        if (mounted) setForecast(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "날씨 정보를 불러오지 못했습니다.");
      } finally {
        if (mounted) setIsLoading(false);
      }
    }
    loadWeather();
    return () => {
      mounted = false;
    };
  }, [days]);

  return (
    <PageContainer
      eyebrow="Paris Weather"
      title="파리 날씨"
      description="일정 선택 전 참고할 수 있는 주간 예보와 날씨별 여행 팁입니다."
      action={
        <label className="trip-selector">
          <span>예보 기간</span>
          <select value={days} onChange={(event) => setDays(Number(event.target.value))}>
            <option value={5}>5일</option>
            <option value={7}>7일</option>
            <option value={10}>10일</option>
          </select>
        </label>
      }
    >
      {isLoading ? <LoadingState label="파리 날씨를 확인하는 중입니다" /> : null}
      {error ? <p className="form-error">{error}</p> : null}
      {!isLoading && !forecast ? <EmptyState title="날씨 정보가 없습니다" description="잠시 후 다시 시도해 주세요." /> : null}
      {forecast ? (
        <>
          <div className="weather-hero-card">
            <span>{forecast.city}, {forecast.country}</span>
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
