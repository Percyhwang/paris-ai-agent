import { useLanguage } from "../../store/LanguageContext";

export function LoadingState({ label }: { label?: string }) {
  const { language } = useLanguage();
  const fallbackLabel = language === "en" ? "Loading..." : "불러오는 중입니다";

  return (
    <div className="loading-state">
      <div className="loader" />
      <span>{label ?? fallbackLabel}</span>
    </div>
  );
}
