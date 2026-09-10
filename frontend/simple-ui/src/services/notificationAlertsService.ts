import { MOCK_NOTIFICATION_ALERT_CATALOG } from "./notificationAlertsMockData";
import type {
  CatalogUpdatePayload,
  NotificationAlertCatalogItem,
  NotificationAlertType,
} from "../types/notificationAlerts";

/** Flip to `false` once gateway catalog APIs are deployed. */
export const USE_NOTIFICATION_ALERTS_MOCK = true;

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

/** In-memory store so Submit persists across tab switches within the session. */
let mockStore: NotificationAlertCatalogItem[] = MOCK_NOTIFICATION_ALERT_CATALOG.map(cloneItem);

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

  const next: NotificationAlertCatalogItem = {
    ...current,
    channels: payload.channels ? [...payload.channels] : [...current.channels],
    recipient_roles: payload.recipient_roles
      ? {
          ...current.recipient_roles,
          ...payload.recipient_roles,
        }
      : { ...current.recipient_roles },
    thresholds:
      current.type === "ALERT"
        ? payload.thresholds
          ? { ...payload.thresholds }
          : current.thresholds
            ? { ...current.thresholds }
            : undefined
        : undefined,
    enabled: payload.enabled ?? current.enabled,
  };

  mockStore[index] = next;
  return cloneItem(next);
}

/**
 * Catalog service facade. Uses prototype mock data until
 * `USE_NOTIFICATION_ALERTS_MOCK` is flipped off.
 */
export const notificationAlertsService = {
  async listCatalog(
    type: NotificationAlertType,
  ): Promise<NotificationAlertCatalogItem[]> {
    if (USE_NOTIFICATION_ALERTS_MOCK) {
      return listCatalogMock(type);
    }
    // Real API wiring lands with gateway deployment (AI4IDS-3094).
    throw new Error(
      "Notification/Alert catalog API is not wired yet. Keep USE_NOTIFICATION_ALERTS_MOCK=true.",
    );
  },

  async updateCatalog(
    name: string,
    payload: CatalogUpdatePayload,
  ): Promise<NotificationAlertCatalogItem> {
    if (USE_NOTIFICATION_ALERTS_MOCK) {
      return updateCatalogMock(name, payload);
    }
    throw new Error(
      "Notification/Alert catalog API is not wired yet. Keep USE_NOTIFICATION_ALERTS_MOCK=true.",
    );
  },
};
