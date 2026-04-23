import { apiRequest } from "./apiClient";
import type { WeatherDay, WeatherForecast } from "../types";

export const weatherService = {
  getCurrentParisWeather(): Promise<WeatherDay & { city: string }> {
    return apiRequest<WeatherDay & { city: string }>("/weather/paris", { auth: false });
  },

  getParisForecast(days = 7): Promise<WeatherForecast> {
    return apiRequest<WeatherForecast>(`/weather/paris/forecast?days=${days}`, { auth: false });
  },
};
