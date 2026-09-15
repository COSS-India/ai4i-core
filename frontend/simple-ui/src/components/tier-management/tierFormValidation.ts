/**
 * Quota validation rules for Tier Management.
 *
 * Mirrors platform-core-service's `TierQuotaIn`
 * (app/schemas/pay_per_use/tier.py), so an oversized or fractional limit
 * gets an inline error instead of an unexplained 422.
 *
 * Shared by the Create/Edit Tier form and the Schedule quota change modal —
 * both post through the same schema, so both owe the same verdict.
 */

/** `limit` — upper bound carried by `TierQuotaIn` (`le=100_000_000_000`). */
export const QUOTA_LIMIT_MAX = 100_000_000_000;

/** Grouped form of the cap, for hint and error copy. */
export const QUOTA_LIMIT_MAX_LABEL = QUOTA_LIMIT_MAX.toLocaleString("en-US");

/**
 * Returns a user-facing message for the first problem found, or null when the
 * limit is acceptable.
 *
 * `limit` is typed `int` on the backend, so a fractional value 422s however
 * small the fraction — rejecting it here is what keeps the form's verdict and
 * the API's in agreement. The backend's `ge=0` is tightened to strictly
 * greater than 0, since a zero quota grants nothing.
 */
export const validateQuotaLimit = (value: string): string | null => {
  const trimmed = value.trim();
  if (!trimmed) {
    return "Limit is required.";
  }
  const limitNum = Number(trimmed);
  if (!Number.isFinite(limitNum)) {
    return "Limit must be a number.";
  }
  if (limitNum <= 0) {
    return "Limit must be greater than 0.";
  }
  if (!Number.isInteger(limitNum)) {
    return "Limit must be a whole number.";
  }
  if (limitNum > QUOTA_LIMIT_MAX) {
    return `Limit must not exceed ${QUOTA_LIMIT_MAX_LABEL}.`;
  }
  return null;
};
