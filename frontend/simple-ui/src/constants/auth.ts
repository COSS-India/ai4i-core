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
