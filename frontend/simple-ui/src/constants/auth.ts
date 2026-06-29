// Password policy and set-password token statuses

/** Password policy — keep in sync with auth-service PASSWORD_MIN/MAX_LENGTH. */
export const PASSWORD_POLICY = {
  MIN_LENGTH: 8,
  MAX_LENGTH: 64,
} as const;

/** Set-password token validation statuses (auth-service). */
export const SET_PASSWORD_TOKEN = {
  STATUS: {
    VALID: "valid",
    EXPIRED: "expired",
    INVALID: "invalid",
    USED: "used",
  },
} as const;

export type SetPasswordTokenStatusValue =
  (typeof SET_PASSWORD_TOKEN.STATUS)[keyof typeof SET_PASSWORD_TOKEN.STATUS];

export function isSetPasswordTokenStatus(
  actual: string,
  expected: SetPasswordTokenStatusValue
): boolean {
  return actual.trim().toLowerCase() === expected;
}

export const LOCAL_STORAGE_KEYS = {
  ACCESS_TOKEN: "access_token",
  REFRESH_TOKEN: "refresh_token",
  REMEMBER_ME: "remember_me",
  LOGIN_TIMESTAMP: "login_timestamp",
  USER: "user",
} as const;

export const SESSION_STORAGE_KEYS = {
  inferenceKeyHexDisplayCache: "ai4i_sess_inference_key_hex_v1",
  ANONYMOUS_SESSION_ID: "anonymous_session_id",
  TRY_IT_REQUEST_COUNT: "tryit_request_count",
  TRY_IT_FIRST_REQUEST_TIME: "tryit_first_request_time",
  REMEMBER_ME: "remember_me",
  AUTH_SESSION_REVOKED: "ai4i:auth:session-revoked",
  USER: "user",
} as const;

export const AUTH_EVENTS = {
  UPDATED: "auth:updated",
} as const;
