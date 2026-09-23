import { INSTITUTION } from "../config/constants";

/** Catalog type discriminator — matches platform-core `NotificationType`. */
export type NotificationAlertType = "NOTIFICATION" | "ALERT";

export type NotificationAlertModule = "TIER" | "BUDGET" | "QUOTA";

export type NotificationChannel = "EMAIL" | "SMS" | "SLACK" | "WHATSAPP" | string;

/** API recipient-role keys (LEGAL_RECIPIENT_ROLES). */
export type RecipientRoleKey = "TENANT ADMIN" | "ADMIN";

/**
 * One configurable alert band, mirroring platform-core `ThresholdBand`.
 * A band has no id or name — `percentage` is what identifies it to the
 * user and is itself editable, which is why PATCH replaces the whole list
 * rather than merging per key (see `CatalogUpdatePayload.thresholds`).
 */
export interface ThresholdBand {
  percentage: number;
  active: boolean;
}

/**
 * One catalog row for the UI.
 * API fields come from `GET /api/v1/notification-alerts/catalog`.
 * `enabled` is derived from recipient_roles (API has no enabled flag).
 */
export interface NotificationAlertCatalogItem {
  id: number;
  name: string;
  display_name: string;
  description: string;
  type: NotificationAlertType;
  module: NotificationAlertModule;
  channels: NotificationChannel[];
  recipient_roles: Record<RecipientRoleKey, boolean>;
  /** Present only on ALERT rows. */
  thresholds?: ThresholdBand[];
  /** True when any recipient role is enabled. */
  enabled: boolean;
  origin: "seeded" | "custom";
}

/** PATCH body accepted by `/notification-alerts/catalog/{name}`. */
export interface CatalogUpdatePayload {
  channels?: NotificationChannel[];
  recipient_roles?: Partial<Record<RecipientRoleKey, boolean>>;
  /** Full replacement of the band list — never a partial merge. */
  thresholds?: ThresholdBand[];
}

export type CatalogStatusFilter = "all" | "enabled" | "disabled";

export const RECIPIENT_ROLE_LABELS: Record<RecipientRoleKey, string> = {
  "TENANT ADMIN": `${INSTITUTION} Admin`,
  ADMIN: "Adopter Admin",
};

/** Default role when enabling a row that has none selected. */
export const DEFAULT_ENABLE_ROLE: RecipientRoleKey = "TENANT ADMIN";

/** Fallback bands when an alert row has no thresholds yet (matches BE seed d5601baf6611). */
export const DEFAULT_ALERT_THRESHOLDS = [70, 80, 90] as const;

/**
 * Band rules, mirroring platform-core `catalog_metadata.py`
 * (MIN/MAX_THRESHOLD_PERCENT, THRESHOLD_BAND_COUNT). Kept in sync by hand —
 * the API re-validates all three rules, so a drift here costs a 422 in the
 * save toast, never a bad write.
 */
export const MIN_THRESHOLD_PERCENT = 1;
export const MAX_THRESHOLD_PERCENT = 99;
export const THRESHOLD_BAND_COUNT = 3;

export function normalizeRecipientRoles(
  roles: Record<string, boolean> | null | undefined,
): Record<RecipientRoleKey, boolean> {
  return {
    "TENANT ADMIN": Boolean(roles?.["TENANT ADMIN"]),
    ADMIN: Boolean(roles?.ADMIN),
  };
}

export function isCatalogItemEnabled(
  roles: Record<string, boolean> | null | undefined,
): boolean {
  return Object.values(roles ?? {}).some(Boolean);
}

/**
 * Bands to render for a row, sorted by percentage. The BE requires exactly
 * THRESHOLD_BAND_COUNT (3) bands on every PATCH, so a row that has none yet
 * falls back to the seed percentages (all off) — the draft is always a
 * complete, submittable set.
 */
export function bandsForItem(
  thresholds: ThresholdBand[] | undefined,
): ThresholdBand[] {
  if (!thresholds || thresholds.length === 0) {
    return DEFAULT_ALERT_THRESHOLDS.map((percentage) => ({
      percentage,
      active: false,
    }));
  }
  return [...thresholds].sort((a, b) => a.percentage - b.percentage);
}

/**
 * A band as the user is editing it. `percentage` is raw input text, not a
 * number: an `<input>` legitimately passes through "" and "7" on the way to
 * "75", and parsing those to NaN/7 eagerly would either blank the field or
 * fight the user's typing. Parsed and validated when the editor is applied
 * instead (see `validateThresholdDrafts`).
 */
export interface ThresholdDraftBand {
  percentage: string;
  active: boolean;
}

export interface ThresholdValidation {
  /** Index-aligned with the drafts; empty string where the band is fine. */
  bandErrors: string[];
  /** Row-level problem (duplicates / wrong count), else null. */
  rowError: string | null;
  /** Parsed bands, or null when anything above is set. */
  bands: ThresholdBand[] | null;
}

export function toThresholdDrafts(
  thresholds: ThresholdBand[] | undefined,
): ThresholdDraftBand[] {
  return bandsForItem(thresholds).map((band) => ({
    percentage: String(band.percentage),
    active: band.active,
  }));
}

/**
 * Applies the same three rules the API enforces (exactly
 * THRESHOLD_BAND_COUNT bands, each a whole percent in
 * MIN..MAX_THRESHOLD_PERCENT, all distinct) so an invalid set is caught on
 * the editor's Apply button rather than as a per-row 422 halfway through
 * saving.
 */
export function validateThresholdDrafts(
  drafts: ThresholdDraftBand[],
): ThresholdValidation {
  const bandErrors = drafts.map(() => "");
  let rowError: string | null = null;

  const parsed = drafts.map((draft, i) => {
    const raw = draft.percentage.trim();
    if (!raw) {
      bandErrors[i] = "Required";
      return null;
    }
    // Reject "7.5", "7e1", "+7" and friends before Number() quietly accepts
    // them — the API takes whole percents only.
    if (!/^\d+$/.test(raw)) {
      bandErrors[i] = "Whole number only";
      return null;
    }
    const value = Number(raw);
    if (value < MIN_THRESHOLD_PERCENT || value > MAX_THRESHOLD_PERCENT) {
      bandErrors[i] = `${MIN_THRESHOLD_PERCENT}-${MAX_THRESHOLD_PERCENT} only`;
      return null;
    }
    return { percentage: value, active: draft.active };
  });

  if (drafts.length !== THRESHOLD_BAND_COUNT) {
    rowError = `Exactly ${THRESHOLD_BAND_COUNT} thresholds are required.`;
  }

  const seen = new Map<number, number>();
  parsed.forEach((band, i) => {
    if (!band) return;
    const first = seen.get(band.percentage);
    if (first === undefined) {
      seen.set(band.percentage, i);
      return;
    }
    rowError = "Thresholds must be unique.";
    bandErrors[i] = bandErrors[i] || "Duplicate";
    bandErrors[first] = bandErrors[first] || "Duplicate";
  });

  const valid =
    !rowError && parsed.every((band): band is ThresholdBand => band !== null);

  return {
    bandErrors,
    rowError,
    bands: valid ? (parsed as ThresholdBand[]) : null,
  };
}

/**
 * Position-wise comparison of two draft sets, on the raw text.
 *
 * Deliberately not a parse-then-compare: this answers "has the user touched
 * this row", and an untouched row must compare equal even if what the API
 * sent would fail validation (a row holding the wrong number of bands, say).
 * Parsing first would report such a row as permanently dirty.
 */
export function draftBandsEqual(
  a: ThresholdDraftBand[],
  b: ThresholdDraftBand[],
): boolean {
  if (a.length !== b.length) return false;
  return a.every(
    (band, i) =>
      band.percentage === b[i].percentage && band.active === b[i].active,
  );
}

/** Order-insensitive band-list comparison (percentage + active). */
export function bandsEqual(
  a: ThresholdBand[] | undefined,
  b: ThresholdBand[] | undefined,
): boolean {
  const left = bandsForItem(a);
  const right = bandsForItem(b);
  if (left.length !== right.length) return false;
  return left.every(
    (band, i) =>
      band.percentage === right[i].percentage && band.active === right[i].active,
  );
}
