import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { getStoredLanguage, normalizeLanguage, persistLanguage, type Language } from "../i18n/config";
import { useAuth } from "./AuthContext";

type LanguageContextValue = {
  language: Language;
  setLanguage: (language: Language) => Promise<void>;
};

const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated, updatePreferences } = useAuth();
  const [language, setLanguageState] = useState<Language>(() => getStoredLanguage());

  useEffect(() => {
    persistLanguage(language);
  }, [language]);

  useEffect(() => {
    const preferred = user?.preferences?.language ? normalizeLanguage(user.preferences.language) : null;
    if (!preferred) return;
    setLanguageState((current) => (current === preferred ? current : preferred));
  }, [user?.id, user?.preferences?.language]);

  const setLanguage = useCallback(async (nextLanguage: Language) => {
    if (nextLanguage === language) return;
    persistLanguage(nextLanguage);
    setLanguageState(nextLanguage);

    if (isAuthenticated && user && normalizeLanguage(user.preferences.language) !== nextLanguage) {
      try {
        await updatePreferences({ language: nextLanguage });
      } catch {
        // Keep the local choice even if profile sync fails.
      }
    }
  }, [isAuthenticated, language, updatePreferences, user]);

  const value = useMemo(
    () => ({
      language,
      setLanguage,
    }),
    [language, setLanguage],
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error("useLanguage must be used within LanguageProvider");
  }
  return context;
}
