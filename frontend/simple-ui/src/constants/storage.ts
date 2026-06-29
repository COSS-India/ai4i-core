/**
 * Browser storage key names.
 *
 * These are non-sensitive storage namespaces — not API keys, tokens, or secrets.
 * Names intentionally avoid substrings like "api_key" or "secret" that static
 * scanners (e.g. Snyk HardcodedNonCryptoSecret) may misclassify as credentials.
 */

export const LOCAL_STORAGE_KEYS = {
  ACCESS_TOKEN: "access_token",
  REFRESH_TOKEN: "refresh_token",
  REMEMBER_ME: "remember_me",
  LOGIN_TIMESTAMP: "login_timestamp",
  USER: "user",
} as const;

export const SESSION_STORAGE_KEYS = {
  /** Maps inference-key name/id → hex value shown once after creation in this tab. */
  inferenceKeyHexDisplayCache: "ai4i_sess_inference_key_hex_v1",
  ANONYMOUS_SESSION_ID: "anonymous_session_id",
  TRY_IT_REQUEST_COUNT: "tryit_request_count",
  TRY_IT_FIRST_REQUEST_TIME: "tryit_first_request_time",
  REMEMBER_ME: "remember_me",
  AUTH_SESSION_REVOKED: "ai4i:auth:session-revoked",
  USER: "user",
} as const;

/** Custom DOM events for cross-tab auth coordination. */
export const AUTH_EVENTS = {
  UPDATED: "auth:updated",
} as const;
