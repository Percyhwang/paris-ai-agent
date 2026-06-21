import { getStoredLanguage } from "../i18n/config";
import type { AuthResponse, User, UserPreferences } from "../types";

const STATIC_DEMO_ACCESS_TOKEN = "static-demo-access-token";
const STATIC_DEMO_REFRESH_TOKEN = "static-demo-refresh-token";
const STATIC_DEMO_USER_KEY = "paris_static_demo_user";

type UserUpdatePayload = {
  name?: string;
  profile_image?: string | null;
  preferences?: UserPreferences;
};

export function isStaticDemoAuthEnabled(): boolean {
  return import.meta.env.VITE_STATIC_DEMO_AUTH === "true";
}

export function isStaticDemoAccessToken(accessToken?: string | null): boolean {
  return accessToken === STATIC_DEMO_ACCESS_TOKEN;
}

export function getStaticDemoUser(): User {
  const stored = localStorage.getItem(STATIC_DEMO_USER_KEY);
  if (stored) {
    try {
      return JSON.parse(stored) as User;
    } catch {
      localStorage.removeItem(STATIC_DEMO_USER_KEY);
    }
  }

  const now = new Date().toISOString();
  return {
    id: "static-demo-user",
    google_id: "static-demo-google-id",
    email: "paris.traveler@example.com",
    name: "Paris Demo Traveler",
    profile_image: null,
    preferences: {
      travel_style: ["relaxed", "balanced"],
      favorite_categories: ["museum", "landmark", "cafe"],
      budget_currency: "EUR",
      language: getStoredLanguage(),
    },
    trips: [],
    created_at: now,
    updated_at: now,
  };
}

export function saveStaticDemoUser(user: User): User {
  localStorage.setItem(STATIC_DEMO_USER_KEY, JSON.stringify(user));
  return user;
}

export function createStaticDemoAuthResponse(): AuthResponse {
  const user = saveStaticDemoUser(getStaticDemoUser());
  return {
    user,
    tokens: {
      access_token: STATIC_DEMO_ACCESS_TOKEN,
      refresh_token: STATIC_DEMO_REFRESH_TOKEN,
      token_type: "bearer",
      expires_in: 60 * 60 * 24 * 7,
    },
  };
}

export function updateStaticDemoUser(payload: UserUpdatePayload): User {
  const current = getStaticDemoUser();
  return saveStaticDemoUser({
    ...current,
    ...payload,
    preferences: payload.preferences ?? current.preferences,
    updated_at: new Date().toISOString(),
  });
}

export function clearStaticDemoUser(): void {
  localStorage.removeItem(STATIC_DEMO_USER_KEY);
}
