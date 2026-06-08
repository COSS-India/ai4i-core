/**
 * Login, registration, password, email verification, and OAuth flows.
 */

import type {
  LoginRequest,
  LoginResponse,
  LogoutRequest,
  LogoutResponse,
  PasswordResetConfirm,
  PasswordResetRequest,
  RegisterRequest,
  ResendVerificationRequest,
  SetPasswordRequest,
  SetPasswordStatusResponse,
  VerifyEmailRequest,
  OAuth2Provider,
} from "../../types/auth";
import { z } from "zod";
import { apiService } from "../api";
import { authUnwrappedSchema } from "../dto/authUnwrappedSchema";
import {
  checkEmailExistsResponseSchema,
  guestServicesListSchema,
  loginResponseSchema,
  logoutResponseSchema,
  messageResponseSchema,
  oauth2ProviderSchema,
  registerResponseSchema,
  resetPasswordResponseSchema,
  setPasswordStatusResponseSchema,
} from "../dto/schemas/auth";
import { apiEndpoints } from "../apiEndpoints";
import { ApiValidationError } from "../dto/apiValidationError";
import { authValidatedRequest, AUTH_BASE_URL } from "./request";
import {
  clearAuthTokens,
  clearStoredUser,
  getRefreshToken,
  setAccessToken,
  setRefreshToken,
} from "./session";

const authPath = apiEndpoints.auth.paths;

export async function register(
  data: RegisterRequest
): Promise<{ user_id: string; email: string; username: string; message: string }> {
  return authValidatedRequest(
    authPath.register,
    authUnwrappedSchema(registerResponseSchema),
    {
      method: "POST",
      body: JSON.stringify(data),
    },
    { withAuth: false }
  );
}

export async function login(data: LoginRequest): Promise<LoginResponse> {
  const response = await authValidatedRequest(
    authPath.login,
    authUnwrappedSchema(loginResponseSchema),
    {
      method: "POST",
      body: JSON.stringify(data),
    },
    { withAuth: false }
  );

  const rememberMe = data.remember_me ?? true;
  setAccessToken(response.access_token, rememberMe);
  setRefreshToken(response.refresh_token, rememberMe);
  return response;
}

export async function guestLogin(): Promise<LoginResponse> {
  const response = await authValidatedRequest(
    authPath.guestLogin,
    authUnwrappedSchema(loginResponseSchema),
    { method: "POST" },
    { withAuth: false }
  );

  setAccessToken(response.access_token, false);
  setRefreshToken(response.refresh_token, false);
  return response;
}

export async function getGuestEnabledServices(): Promise<unknown> {
  return authValidatedRequest(
    authPath.rolesListGuestServices,
    authUnwrappedSchema(guestServicesListSchema),
    { method: "GET" },
    { withAuth: false }
  );
}

export async function logout(data: LogoutRequest = {}): Promise<LogoutResponse> {
  const refreshToken = getRefreshToken();
  const clearLocalState = () => {
    clearAuthTokens();
    clearStoredUser();
  };

  if (!refreshToken) {
    clearLocalState();
    throw new Error("No refresh token found");
  }

  try {
    const response = await authValidatedRequest(
      authPath.logout,
      authUnwrappedSchema(logoutResponseSchema),
      {
        method: "POST",
        body: JSON.stringify({
          refresh_token: data.refresh_token || refreshToken,
        }),
      }
    );
    clearLocalState();
    return response;
  } catch (error) {
    console.error("Logout API call failed, but clearing local state:", error);
    clearLocalState();
    throw error;
  }
}

export async function requestPasswordReset(
  data: PasswordResetRequest
): Promise<{ message: string }> {
  return authValidatedRequest(
    authPath.forgotPassword,
    authUnwrappedSchema(messageResponseSchema),
    {
      method: "POST",
      body: JSON.stringify(data),
    },
    { withAuth: false }
  );
}

export async function resetPassword(
  data: PasswordResetConfirm
): Promise<{ message: string; sign_out_other_sessions?: boolean }> {
  return authValidatedRequest(
    authPath.resetPassword,
    authUnwrappedSchema(resetPasswordResponseSchema),
    {
      method: "POST",
      body: JSON.stringify(data),
    },
    { withAuth: false }
  );
}

export async function getSetPasswordStatus(token: string): Promise<SetPasswordStatusResponse> {
  const url = `${AUTH_BASE_URL}${authPath.setPasswordStatus(token)}`;
  try {
    const res = await apiService.request("GET", url, undefined, {
      responseSchema: setPasswordStatusResponseSchema,
    });
    return res.data;
  } catch (error: unknown) {
    if (error instanceof ApiValidationError) {
      throw error;
    }
    const status = (error as { response?: { status?: number } })?.response?.status;
    return { valid: false, status: "invalid", message: status ? `HTTP ${status}` : "Network error" };
  }
}

export async function setPasswordWithToken(data: SetPasswordRequest): Promise<{ message: string }> {
  return authValidatedRequest(
    authPath.setPassword,
    authUnwrappedSchema(messageResponseSchema),
    {
      method: "POST",
      body: JSON.stringify(data),
    },
    { withAuth: false }
  );
}

export async function verifyEmail(data: VerifyEmailRequest): Promise<{ message: string }> {
  return authValidatedRequest(
    authPath.verifyEmail,
    authUnwrappedSchema(messageResponseSchema),
    {
      method: "POST",
      body: JSON.stringify(data),
    },
    { withAuth: false }
  );
}

export async function resendVerification(
  data: ResendVerificationRequest
): Promise<{ message: string }> {
  return authValidatedRequest(
    authPath.resendVerification,
    authUnwrappedSchema(messageResponseSchema),
    {
      method: "POST",
      body: JSON.stringify(data),
    },
    { withAuth: false }
  );
}

export async function resendSetupLink(
  data: { email: string },
  options: { withAuth?: boolean } = {}
): Promise<{ message: string }> {
  const withAuth = options.withAuth === true;
  return authValidatedRequest(
    authPath.resendSetupLink,
    authUnwrappedSchema(messageResponseSchema),
    {
      method: "POST",
      body: JSON.stringify(data),
    },
    { withAuth }
  );
}

export async function getOAuth2Providers(): Promise<OAuth2Provider[]> {
  return authValidatedRequest(
    authPath.oauth2Providers,
    authUnwrappedSchema(z.array(oauth2ProviderSchema)),
    { method: "GET" }
  );
}

export async function exchangeOAuthCode(code: string): Promise<LoginResponse> {
  return authValidatedRequest(
    authPath.oauth2Exchange,
    authUnwrappedSchema(loginResponseSchema),
    {
      method: "POST",
      body: JSON.stringify({ code }),
    },
    { withAuth: false }
  );
}

export async function checkEmailExists(
  email: string,
  options: { withAuth?: boolean } = {}
): Promise<boolean> {
  const trimmed = email.trim();
  const withAuth = options.withAuth !== false;
  const result = await authValidatedRequest(
    `${authPath.checkEmail}?email=${encodeURIComponent(trimmed)}`,
    authUnwrappedSchema(checkEmailExistsResponseSchema),
    { method: "GET" },
    { withAuth }
  );
  return result.exists;
}
