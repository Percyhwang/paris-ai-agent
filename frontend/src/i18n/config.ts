export type Language = "ko" | "en";

export const LANGUAGE_STORAGE_KEY = "paris_language";

export function normalizeLanguage(value?: string | null): Language {
  if (!value) return "ko";
  const lowered = value.trim().toLowerCase();
  return lowered.startsWith("en") ? "en" : "ko";
}

export function getStoredLanguage(): Language {
  if (typeof window === "undefined") return "ko";
  return normalizeLanguage(
    window.localStorage.getItem(LANGUAGE_STORAGE_KEY) ??
      document.documentElement.lang ??
      window.navigator.language,
  );
}

export function persistLanguage(language: Language) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  document.documentElement.lang = language;
}

export function getIntlLocale(language?: Language | string | null) {
  return normalizeLanguage(language) === "en" ? "en-US" : "ko-KR";
}

export function getGoogleLocale(language?: Language | string | null) {
  return normalizeLanguage(language) === "en" ? "en" : "ko";
}
