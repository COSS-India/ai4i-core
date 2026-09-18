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
