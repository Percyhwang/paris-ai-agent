import { getIntlLocale, getStoredLanguage } from "../i18n/config";

export function formatDate(value?: string | null, language = getStoredLanguage()): string {
  if (!value) return language === "en" ? "Date not set" : "날짜 미정";
  return new Intl.DateTimeFormat(getIntlLocale(language), {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

export function formatCurrency(value: number, currency = "EUR", language = getStoredLanguage()): string {
  return new Intl.NumberFormat(getIntlLocale(language), {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

export function todayInputValue(): string {
  return new Date().toISOString().slice(0, 10);
}
