/** Catalog type discriminator — matches platform-core `NotificationType`. */
export type NotificationAlertType = "NOTIFICATION" | "ALERT";

export type NotificationAlertModule = "TIER" | "BUDGET" | "QUOTA";

export type NotificationChannel = "EMAIL" | "SMS" | "SLACK" | "WHATSAPP" | string;

/** API recipient-role keys (LEGAL_RECIPIENT_ROLES). */
export type RecipientRoleKey = "TENANT ADMIN" | "ADMIN";

/**
 * One catalog row for the UI.
 * API fields come from `GET /api/v1/notification-alerts/catalog`.
 * `enabled` / `origin` are UI helpers (API has no explicit enabled flag).
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
  thresholds?: Record<string, boolean>;
  /** True when any recipient role is enabled. */
  enabled: boolean;
  origin: "seeded" | "custom";
}

/** PATCH body accepted by `/notification-alerts/catalog/{name}`. */
export interface CatalogUpdatePayload {
  channels?: NotificationChannel[];
  recipient_roles?: Partial<Record<RecipientRoleKey, boolean>>;
  thresholds?: Record<string, boolean>;
  /**
   * UI-only. Mapped to recipient_roles on the wire:
   * disabled → both roles false; enabled → draft roles as-is.
   */
  enabled?: boolean;
}

export type CatalogStatusFilter = "all" | "enabled" | "disabled";

export const RECIPIENT_ROLE_LABELS: Record<RecipientRoleKey, string> = {
  "TENANT ADMIN": "Tenant Admin",
  ADMIN: "Adopter Admin",
};

/** Tenant Admin is only editable for these notification names (prototype rule). */
export const TENANT_ADMIN_EDITABLE_NAMES = new Set([
  "TIER_ASSIGNED",
  "TIER_CHANGED",
]);

/** Fallback bands when an alert row has no thresholds keys yet (matches BE seed). */
export const DEFAULT_ALERT_THRESHOLDS = ["50", "75", "90"] as const;

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

export function thresholdKeysForItem(
  thresholds: Record<string, boolean> | undefined,
): string[] {
  const keys = Object.keys(thresholds ?? {});
  if (keys.length === 0) return [...DEFAULT_ALERT_THRESHOLDS];
  return keys.sort((a, b) => Number(a) - Number(b));
}
