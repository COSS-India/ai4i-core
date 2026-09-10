import type { NotificationAlertCatalogItem } from "../types/notificationAlerts";

/**
 * Mock catalog seeded from the reference prototype:
 * https://mmanimegalai.github.io/html/notification-alert-prototype.html
 *
 * Role keys use the API contract (`TENANT ADMIN` / `ADMIN`).
 * Threshold bands use the prototype's 70/80/90 (backend seed uses 50/75/90).
 */
export const MOCK_NOTIFICATION_ALERT_CATALOG: NotificationAlertCatalogItem[] = [
  {
    id: 1,
    name: "TIER_ASSIGNED",
    display_name: "Tier Assigned",
    description:
      "Fires when the Adopter Admin assigns a Tier to a tenant for the first time.",
    type: "NOTIFICATION",
    module: "TIER",
    channels: ["EMAIL"],
    recipient_roles: { "TENANT ADMIN": true, ADMIN: false },
    enabled: true,
    origin: "seeded",
  },
  {
    id: 2,
    name: "TIER_CHANGED",
    display_name: "Tier Changed",
    description:
      "Fires when the Adopter Admin moves a tenant from one Tier to a different Tier.",
    type: "NOTIFICATION",
    module: "TIER",
    channels: ["EMAIL"],
    recipient_roles: { "TENANT ADMIN": true, ADMIN: false },
    enabled: true,
    origin: "seeded",
  },
  {
    id: 3,
    name: "BUDGET_ASSIGNED",
    display_name: "Budget Assigned",
    description:
      "Fires when the Adopter Admin assigns a Budget to a tenant for the first time.",
    type: "NOTIFICATION",
    module: "BUDGET",
    channels: ["EMAIL"],
    recipient_roles: { "TENANT ADMIN": true, ADMIN: false },
    enabled: false,
    origin: "seeded",
  },
  {
    id: 4,
    name: "BUDGET_UPDATED",
    display_name: "Budget Updated",
    description:
      "Fires when the Adopter Admin changes an existing Budget amount for a tenant.",
    type: "NOTIFICATION",
    module: "BUDGET",
    channels: ["EMAIL"],
    recipient_roles: { "TENANT ADMIN": true, ADMIN: false },
    enabled: false,
    origin: "seeded",
  },
  {
    id: 5,
    name: "QUOTA_EXHAUSTED",
    display_name: "Quota Exhausted",
    description:
      "Fires when a tenant's Quota reaches 100% and new requests are blocked.",
    type: "NOTIFICATION",
    module: "QUOTA",
    channels: ["EMAIL"],
    recipient_roles: { "TENANT ADMIN": true, ADMIN: false },
    enabled: false,
    origin: "seeded",
  },
  {
    id: 6,
    name: "BUDGET_EXHAUSTED",
    display_name: "Budget Exhausted",
    description:
      "Fires when a tenant's Budget is fully depleted and new requests are blocked.",
    type: "NOTIFICATION",
    module: "BUDGET",
    channels: ["EMAIL"],
    recipient_roles: { "TENANT ADMIN": true, ADMIN: false },
    enabled: false,
    origin: "seeded",
  },
  {
    id: 7,
    name: "QUOTA_THRESHOLD",
    display_name: "Quota Threshold Alert",
    description:
      "Fires once when this tenant's consumption against a Quota crosses a configured threshold.",
    type: "ALERT",
    module: "QUOTA",
    channels: ["EMAIL"],
    recipient_roles: { "TENANT ADMIN": true, ADMIN: false },
    thresholds: { "70": true, "80": true, "90": true },
    enabled: true,
    origin: "seeded",
  },
  {
    id: 8,
    name: "BUDGET_THRESHOLD",
    display_name: "Budget Threshold Alert",
    description:
      "Fires once when this tenant's spend against a Budget crosses a configured threshold.",
    type: "ALERT",
    module: "BUDGET",
    channels: ["EMAIL"],
    recipient_roles: { "TENANT ADMIN": true, ADMIN: false },
    thresholds: { "70": true, "80": true, "90": true },
    enabled: false,
    origin: "seeded",
  },
];
