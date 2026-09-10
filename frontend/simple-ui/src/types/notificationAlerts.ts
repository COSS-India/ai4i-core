/** Catalog type discriminator — matches platform-core `NotificationType`. */
export type NotificationAlertType = "NOTIFICATION" | "ALERT";

export type NotificationAlertModule = "TIER" | "BUDGET" | "QUOTA" | "RATE_LIMIT";

export type NotificationChannel = "EMAIL";

/** API recipient-role keys (LEGAL_RECIPIENT_ROLES). */
export type RecipientRoleKey = "TENANT ADMIN" | "ADMIN";

/**
 * One catalog row. Shape mirrors
 * `GET /api/v1/notification-alerts/catalog` `CatalogItem`.
 *
 * `enabled` is a UI/mock convenience matching the prototype row checkbox.
 * When real APIs land, treat a row as enabled when any recipient role is true
 * unless the backend adds an explicit flag.
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
  /** Prototype "status" — Enabled/Disabled. */
  enabled: boolean;
  origin: "seeded" | "custom";
}

export interface CatalogUpdatePayload {
  channels?: NotificationChannel[];
  recipient_roles?: Partial<Record<RecipientRoleKey, boolean>>;
  thresholds?: Record<string, boolean>;
  /** Mock-only until backend supports an enabled flag. */
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

export const STANDARD_ALERT_THRESHOLDS = ["70", "80", "90"] as const;
