/**
 * Token storage, session lifecycle, and current-user session APIs.
 */

import type {
  PasswordChangeRequest,
  TokenRefreshResponse,
  TokenValidationResponse,
  User,
} from "../../types/auth";
import { authUnwrappedSchema } from "../dto/authUnwrappedSchema";
import {
  messageResponseSchema,
  tokenRefreshResponseSchema,
  tokenValidationResponseSchema,
  userSchema,
} from "../dto/schemas/auth";
import { apiEndpoints } from "../apiEndpoints";
import {
  getStoredAccessToken,
  getStoredRefreshToken,
  getRememberMeFromStorage,
  setStoredAccessToken,
  setStoredRefreshToken,
  clearTokenStorage,
} from "../../utils/tokenStorage";
import { authValidatedRequest } from "./request";

const authPath = apiEndpoints.auth.paths;

let refreshPromise: Promise<TokenRefreshResponse> | null = null;

function setLoginTimestamp(): void {
  if (typeof window === "undefined") return;
  const timestamp = Date.now().toString();
  localStorage.removeItem("login_timestamp");
  sessionStorage.removeItem("login_timestamp");
  sessionStorage.setItem("login_timestamp", timestamp);
}

function decodeToken(token: string): { exp?: number } | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    return JSON.parse(atob(parts[1]));
  } catch (error) {
    console.error("Failed to decode token:", error);
    return null;
  }
}

export function getAccessToken(): string | null {
  return getStoredAccessToken();
}

export function setAccessToken(token: string, rememberMe = true): void {
  if (typeof window === "undefined") return;
  setStoredAccessToken(token, rememberMe);
  setLoginTimestamp();
}

export function getRefreshToken(): string | null {
  return getStoredRefreshToken();
}

export function setRefreshToken(token: string, rememberMe = true): void {
  if (typeof window === "undefined") return;
  setStoredRefreshToken(token, rememberMe);
}

export function clearAuthTokens(): void {
  clearTokenStorage();
}

export function isAuthenticated(): boolean {
  return !!getAccessToken();
}

export function getStoredUser(): User | null {
  if (typeof window === "undefined") return null;
  const userStr = sessionStorage.getItem("user");
  return userStr ? JSON.parse(userStr) : null;
}

export function setStoredUser(user: User): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem("user");
  sessionStorage.removeItem("user");
  sessionStorage.setItem("user", JSON.stringify(user));
}

export function clearStoredUser(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem("user");
  sessionStorage.removeItem("user");
}

export function getTokenExpiry(): number | null {
  const token = getAccessToken();
  if (!token) return null;
  const payload = decodeToken(token);
  if (!payload?.exp) return null;
  return payload.exp * 1000;
}

export function isTokenExpired(): boolean {
  const expiry = getTokenExpiry();
  if (!expiry) return true;
  return Date.now() >= expiry;
}

export function isTokenExpiringSoon(thresholdMinutes = 5): boolean {
  const expiry = getTokenExpiry();
  if (!expiry) return true;
  const thresholdMs = thresholdMinutes * 60 * 1000;
  return expiry - Date.now() < thresholdMs;
}

export function getTimeUntilExpiry(): number | null {
  const expiry = getTokenExpiry();
  if (!expiry) return null;
  return expiry - Date.now();
}

export function getLoginTimestamp(): number | null {
  if (typeof window === "undefined") return null;
  const timestampStr = sessionStorage.getItem("login_timestamp");
  return timestampStr ? parseInt(timestampStr, 10) : null;
}

export function isSessionExpired(): boolean {
  const loginTimestamp = getLoginTimestamp();
  if (!loginTimestamp) return true;
  const rememberMe = getRememberMeFromStorage();
  const sessionDurationMs = rememberMe ? 7 * 24 * 60 * 60 * 1000 : 24 * 60 * 60 * 1000;
  return Date.now() - loginTimestamp >= sessionDurationMs;
}

export function getTimeUntilSessionExpiry(): number | null {
  const loginTimestamp = getLoginTimestamp();
  if (!loginTimestamp) return null;
  const rememberMe = getRememberMeFromStorage();
  const sessionDurationMs = rememberMe ? 7 * 24 * 60 * 60 * 1000 : 24 * 60 * 60 * 1000;
  const timeRemaining = sessionDurationMs - (Date.now() - loginTimestamp);
  return timeRemaining > 0 ? timeRemaining : 0;
}

export async function refreshToken(): Promise<TokenRefreshResponse> {
  const refreshTokenValue = getRefreshToken();
  if (!refreshTokenValue) {
    throw new Error("No refresh token available");
  }

  if (refreshPromise !== null) {
    return refreshPromise;
  }

  refreshPromise = (async () => {
    try {
      const response = await authValidatedRequest(
        authPath.refresh,
        authUnwrappedSchema(tokenRefreshResponseSchema),
        {
          method: "POST",
          body: JSON.stringify({ refresh_token: refreshTokenValue }),
        },
        { withAuth: false }
      );

      setAccessToken(response.access_token, getRememberMeFromStorage());
      return response;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

export async function validateToken(): Promise<TokenValidationResponse> {
  return authValidatedRequest(
    authPath.validate,
    authUnwrappedSchema(tokenValidationResponseSchema),
    { method: "GET" }
  );
}

export async function getCurrentUser(): Promise<User> {
  return authValidatedRequest(
    authPath.me,
    authUnwrappedSchema(userSchema),
    { method: "GET" },
    { timeoutMs: 20000 }
  );
}

export async function updateCurrentUser(data: Partial<User>): Promise<User> {
  return authValidatedRequest(authPath.me, authUnwrappedSchema(userSchema), {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function changePassword(data: PasswordChangeRequest): Promise<{ message: string }> {
  return authValidatedRequest(
    authPath.changePassword,
    authUnwrappedSchema(messageResponseSchema),
    {
      method: "POST",
      body: JSON.stringify(data),
    }
  );
}

export async function refreshIfExpiringSoon(thresholdMinutes = 5): Promise<boolean> {
  if (!isAuthenticated()) return false;
  if (!isTokenExpiringSoon(thresholdMinutes)) return true;
  try {
    await refreshToken();
    return true;
  } catch (error) {
    console.error("Failed to refresh token:", error);
    return false;
  }
}

export async function ensureValidToken(): Promise<boolean> {
  if (!isAuthenticated()) return false;

  try {
    await validateToken();
    return true;
  } catch {
    try {
      await refreshToken();
      return true;
    } catch {
      clearAuthTokens();
      clearStoredUser();
      return false;
    }
  }
}
