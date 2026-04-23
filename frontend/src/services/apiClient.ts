import type { ApiResponse, TokenPair } from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";
const ACCESS_TOKEN_KEY = "paris_access_token";
const REFRESH_TOKEN_KEY = "paris_refresh_token";

type ApiRequestOptions = RequestInit & {
  auth?: boolean;
  retryOnUnauthorized?: boolean;
};

export function getStoredTokens(): Pick<TokenPair, "access_token" | "refresh_token"> | null {
  const accessToken = localStorage.getItem(ACCESS_TOKEN_KEY);
  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
  if (!accessToken || !refreshToken) return null;
  return { access_token: accessToken, refresh_token: refreshToken };
}

export function storeTokens(tokens: TokenPair): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const response = await fetchWithAuth(path, { retryOnUnauthorized: true, ...options });
  const envelope = (await response.json()) as ApiResponse<T>;
  if (!response.ok || !envelope.success) {
    throw new Error(envelope.message || envelope.error?.code || "API request failed");
  }
  return envelope.data;
}

async function fetchWithAuth(path: string, options: ApiRequestOptions): Promise<Response> {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }

  if (options.auth !== false) {
    const tokens = getStoredTokens();
    if (tokens?.access_token) {
      headers.set("Authorization", `Bearer ${tokens.access_token}`);
    }
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  if (response.status !== 401 || options.auth === false || !options.retryOnUnauthorized) {
    return response;
  }

  const refreshed = await refreshAccessToken();
  if (!refreshed) {
    clearTokens();
    return response;
  }

  const retryHeaders = new Headers(headers);
  const tokens = getStoredTokens();
  if (tokens?.access_token) {
    retryHeaders.set("Authorization", `Bearer ${tokens.access_token}`);
  }
  return fetch(`${API_BASE_URL}${path}`, { ...options, headers: retryHeaders, retryOnUnauthorized: false } as RequestInit);
}

async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
  if (!refreshToken) return false;

  try {
    const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    const envelope = (await response.json()) as ApiResponse<TokenPair>;
    if (!response.ok || !envelope.success) return false;
    storeTokens(envelope.data);
    return true;
  } catch {
    return false;
  }
}
