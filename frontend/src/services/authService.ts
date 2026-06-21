import { apiRequest, clearTokens, getStoredTokens, storeTokens } from "./apiClient";
import {
  clearStaticDemoUser,
  createStaticDemoAuthResponse,
  getStaticDemoUser,
  isStaticDemoAccessToken,
  isStaticDemoAuthEnabled,
} from "./staticDemoAuth";
import type { AuthResponse, User } from "../types";

export const authService = {
  async loginWithGoogleCredential(credential: string): Promise<AuthResponse> {
    const response = await apiRequest<AuthResponse>("/auth/google/login", {
      method: "POST",
      auth: false,
      body: JSON.stringify({ credential }),
    });
    storeTokens(response.tokens);
    return response;
  },

  async demoLogin(): Promise<AuthResponse> {
    if (isStaticDemoAuthEnabled()) {
      const response = createStaticDemoAuthResponse();
      storeTokens(response.tokens);
      return response;
    }

    return this.loginWithGoogleCredential("dev:paris.traveler@example.com");
  },

  async me(): Promise<User> {
    const tokens = getStoredTokens();
    if (isStaticDemoAuthEnabled() && isStaticDemoAccessToken(tokens?.access_token)) {
      return getStaticDemoUser();
    }

    return apiRequest<User>("/auth/me");
  },

  logout(): void {
    clearTokens();
    if (isStaticDemoAuthEnabled()) {
      clearStaticDemoUser();
    }
  },
};
