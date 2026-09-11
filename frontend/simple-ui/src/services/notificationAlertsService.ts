import apiClient from "./api";
import { apiEndpoints } from "./apiEndpoints";
import { MOCK_NOTIFICATION_ALERT_CATALOG } from "./notificationAlertsMockData";
import {
  catalogListResponseSchema,
  catalogUpdateResponseSchema,
  type ApiCatalogItem,
} from "./dto/schemas/notificationAlerts";
import type {
  CatalogUpdatePayload,
  NotificationAlertCatalogItem,
  NotificationAlertType,
  RecipientRoleKey,
} from "../types/notificationAlerts";
import {
  isCatalogItemEnabled,
  normalizeRecipientRoles,
} from "../types/notificationAlerts";

/**
 * Set `true` only for offline UI work without the gateway.
 * Dev catalog routes are live at `/api/v1/notification-alerts/catalog`.
 */
export const USE_NOTIFICATION_ALERTS_MOCK = false;

const MOCK_LATENCY_MS = 250;

function delay(ms = MOCK_LATENCY_MS): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function cloneItem(item: NotificationAlertCatalogItem): NotificationAlertCatalogItem {
  return {
    ...item,
    channels: [...item.channels],
    recipient_roles: { ...item.recipient_roles },
    thresholds: item.thresholds ? { ...item.thresholds } : undefined,
  };
}

function fromApiItem(item: ApiCatalogItem): NotificationAlertCatalogItem {
  const recipient_roles = normalizeRecipientRoles(item.recipient_roles);
  return {
    id: item.id,
    name: item.name,
    display_name: item.display_name,
    description: item.description,
    type: item.type,
    module: item.module,
    channels: [...item.channels],
    recipient_roles,
    thresholds:
      item.thresholds == null ? undefined : { ...item.thresholds },
    enabled: isCatalogItemEnabled(item.recipient_roles),
    // Catalog is system-seeded only in v1 (no custom create API).
    origin: "seeded",
  };
}

/** In-memory store for mock mode. */
let mockStore: NotificationAlertCatalogItem[] =
  MOCK_NOTIFICATION_ALERT_CATALOG.map(cloneItem);

export function resetNotificationAlertsMockStore(): void {
  mockStore = MOCK_NOTIFICATION_ALERT_CATALOG.map(cloneItem);
}

async function listCatalogMock(
  type: NotificationAlertType,
): Promise<NotificationAlertCatalogItem[]> {
  await delay();
  return mockStore.filter((item) => item.type === type).map(cloneItem);
}

async function updateCatalogMock(
  name: string,
  payload: CatalogUpdatePayload,
): Promise<NotificationAlertCatalogItem> {
  await delay();
  const index = mockStore.findIndex((item) => item.name === name);
  if (index < 0) {
    throw new Error(`Catalog item '${name}' not found.`);
  }

  const current = mockStore[index];
  if (payload.thresholds && current.type === "NOTIFICATION") {
    throw new Error("thresholds is not valid for NOTIFICATION catalog rows.");
  }

  const recipient_roles = normalizeRecipientRoles({
    ...current.recipient_roles,
    ...(payload.recipient_roles ?? {}),
  });
  const enabled =
    payload.enabled !== undefined
      ? payload.enabled
      : isCatalogItemEnabled(recipient_roles);

  const next: NotificationAlertCatalogItem = {
    ...current,
    channels: payload.channels ? [...payload.channels] : [...current.channels],
    recipient_roles: enabled
      ? recipient_roles
      : { "TENANT ADMIN": false, ADMIN: false },
    thresholds:
      current.type === "ALERT"
        ? payload.thresholds
          ? { ...payload.thresholds }
          : current.thresholds
            ? { ...current.thresholds }
            : undefined
        : undefined,
    enabled,
  };

  mockStore[index] = next;
  return cloneItem(next);
}

function toApiUpdateBody(payload: CatalogUpdatePayload): {
  channels?: string[];
  recipient_roles?: Partial<Record<RecipientRoleKey, boolean>>;
  thresholds?: Record<string, boolean>;
} {
  const body: {
    channels?: string[];
    recipient_roles?: Partial<Record<RecipientRoleKey, boolean>>;
    thresholds?: Record<string, boolean>;
  } = {};

  if (payload.channels) {
    body.channels = [...payload.channels];
  }

  if (payload.enabled === false) {
    body.recipient_roles = { "TENANT ADMIN": false, ADMIN: false };
  } else if (payload.recipient_roles) {
    body.recipient_roles = { ...payload.recipient_roles };
  }

  if (payload.thresholds) {
    body.thresholds = { ...payload.thresholds };
  }

  return body;
}

async function listCatalogApi(
  type: NotificationAlertType,
  signal?: AbortSignal,
): Promise<NotificationAlertCatalogItem[]> {
  const response = await apiClient.get(apiEndpoints.notificationAlerts.catalog, {
    params: { type },
    signal,
  });
  const parsed = catalogListResponseSchema.parse(response.data);
  return parsed.data.items.map(fromApiItem);
}

async function updateCatalogApi(
  name: string,
  payload: CatalogUpdatePayload,
): Promise<NotificationAlertCatalogItem> {
  const response = await apiClient.patch(
    apiEndpoints.notificationAlerts.catalogByName(name),
    toApiUpdateBody(payload),
  );
  const parsed = catalogUpdateResponseSchema.parse(response.data);
  return fromApiItem(parsed.data);
}

/**
 * Catalog service — real gateway APIs by default; mock retained for offline UI.
 */
export const notificationAlertsService = {
  async listCatalog(
    type: NotificationAlertType,
    signal?: AbortSignal,
  ): Promise<NotificationAlertCatalogItem[]> {
    if (USE_NOTIFICATION_ALERTS_MOCK) {
      return listCatalogMock(type);
    }
    return listCatalogApi(type, signal);
  },

  async updateCatalog(
    name: string,
    payload: CatalogUpdatePayload,
  ): Promise<NotificationAlertCatalogItem> {
    if (USE_NOTIFICATION_ALERTS_MOCK) {
      return updateCatalogMock(name, payload);
    }
    return updateCatalogApi(name, payload);
  },
};
