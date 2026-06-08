/**
 * Shared authenticated HTTP helper for auth-service endpoints.
 */

import type { ZodTypeAny } from "zod";
import { z } from "zod";
import { API_BASE_URL, apiService } from "../api";
import { apiEndpoints } from "../apiEndpoints";
import { ApiValidationError } from "../dto/apiValidationError";
import { responseIndicatesTenantSuspendedOrInactive } from "../../utils/tenantInactiveApiErrors";
import { clearAuthTokens, clearStoredUser, getAccessToken } from "./session";

export const AUTH_BASE_URL = `${API_BASE_URL}${apiEndpoints.auth.base}`;
const authPath = apiEndpoints.auth.paths;

export async function authValidatedRequest<S extends ZodTypeAny>(
  endpoint: string,
  schema: S,
  options: RequestInit = {},
  requestOpts: { withAuth?: boolean; timeoutMs?: number } = {}
): Promise<z.infer<S>> {
  const url = `${AUTH_BASE_URL}${endpoint}`;
  const withAuth = requestOpts.withAuth !== false;
  const timeoutMs = requestOpts.timeoutMs ?? 10000;

  const defaultHeaders: HeadersInit = {
    "Content-Type": "application/json",
  };

  if (withAuth) {
    const token = getAccessToken();
    if (token) {
      defaultHeaders.Authorization = `Bearer ${token}`;
    }
  }

  const config: RequestInit = {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  };

  try {
    const response = await apiService.request(
      (config.method || "GET") as "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
      url,
      config.body,
      {
        headers: config.headers as Record<string, string>,
        timeout: timeoutMs,
        responseSchema: schema,
      }
    );
    return response.data as z.infer<S>;
  } catch (error: unknown) {
    if (error instanceof ApiValidationError) {
      throw error;
    }
    const err = error as {
      code?: string;
      response?: { status?: number; data?: unknown };
      status?: number;
    };
    if (err?.code === "ECONNABORTED") {
      console.error("Auth service request timed out:", url);
      throw new Error(`Request timeout: Auth service is not responding (timeout: ${timeoutMs}ms)`);
    }

    const status = err?.response?.status;
    const errorData = (err?.response?.data ?? {}) as Record<string, unknown>;

    if (
      withAuth &&
      typeof window !== "undefined" &&
      typeof status === "number" &&
      responseIndicatesTenantSuspendedOrInactive(status, errorData)
    ) {
      try {
        const { forceFrontendSessionEnd } = await import("../../hooks/useAuth");
        forceFrontendSessionEnd();
      } catch {
        clearAuthTokens();
        clearStoredUser();
        window.location.assign("/auth");
      }
      throw new Error("Your organization account is no longer active. Please sign in again.");
    }

    let errorMessage = status ? `HTTP error! status: ${status}` : "Request failed";
    if (errorData?.detail) {
      const d = errorData.detail;
      if (typeof d === "string") {
        errorMessage = d;
      } else if (typeof d === "object" && d !== null && typeof (d as { message?: string }).message === "string") {
        errorMessage = (d as { message: string }).message;
      } else if (typeof d === "object" && d !== null) {
        const msg = (d as { message?: unknown }).message;
        errorMessage = msg != null ? String(msg) : JSON.stringify(d);
      } else {
        errorMessage = String(d);
      }
    } else if (errorData?.message) {
      errorMessage = String(errorData.message);
    } else if (typeof errorData === "string") {
      errorMessage = errorData;
    } else if (Array.isArray(errorData) && errorData.length > 0) {
      errorMessage = errorData
        .map((e: { detail?: { message?: string } | string; message?: string }) =>
          typeof e.detail === "object" && e.detail?.message
            ? e.detail.message
            : (e.detail ?? e.message ?? String(e))
        )
        .join(", ");
    }

    if (withAuth && endpoint !== authPath.changePassword) {
      const errorMessageLower = errorMessage.toLowerCase();
      const isInvalidAuth =
        errorMessageLower.includes("invalid authentication credentials") ||
        errorMessageLower.includes("token expired") ||
        errorMessageLower.includes("token has expired") ||
        errorMessageLower.includes("token is invalid") ||
        errorMessageLower.includes("session expired");

      if (isInvalidAuth && typeof window !== "undefined") {
        clearAuthTokens();
        clearStoredUser();
        window.location.href = "/";
        throw new Error("Session expired. Please sign in again.");
      }
    } else if (!withAuth) {
      if (typeof errorData === "object" && Object.keys(errorData).length > 0) {
        const d = (errorData.detail ?? errorData.message ?? errorData.error) as
          | { message?: unknown }
          | string
          | undefined;
        errorMessage =
          typeof d === "object" && d !== null && d.message != null
            ? String(d.message)
            : d != null
              ? String(d)
              : JSON.stringify(errorData);
      }
    }

    console.error("Auth service request failed:", error);
    const normalizedError = new Error(errorMessage);
    (normalizedError as Error & { status?: number; response?: unknown }).status =
      status ?? err?.status;
    if (err?.response) {
      (normalizedError as Error & { response?: unknown }).response = err.response;
    }
    throw normalizedError;
  }
}
