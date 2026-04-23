import { apiRequest, clearTokens, storeTokens } from "./apiClient";
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
    return this.loginWithGoogleCredential("dev:paris.traveler@example.com");
  },

  async me(): Promise<User> {
    return apiRequest<User>("/auth/me");
  },

  logout(): void {
    clearTokens();
  },
};
