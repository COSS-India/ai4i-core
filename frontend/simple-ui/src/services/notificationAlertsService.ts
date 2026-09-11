import apiClient from "./api";
import { apiEndpoints } from "./apiEndpoints";
import {
  catalogListResponseSchema,
  catalogUpdateResponseSchema,
  type ApiCatalogItem,
} from "./dto/schemas/notificationAlerts";
import type {
  CatalogUpdatePayload,
  NotificationAlertCatalogItem,
  NotificationAlertType,
} from "../types/notificationAlerts";
import {
  isCatalogItemEnabled,
  normalizeRecipientRoles,
} from "../types/notificationAlerts";

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
    thresholds: item.thresholds == null ? undefined : { ...item.thresholds },
    enabled: isCatalogItemEnabled(item.recipient_roles),
    // Catalog is system-seeded only in v1 (no custom create API).
    origin: "seeded",
  };
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
  const body: CatalogUpdatePayload = {};
  if (payload.channels) body.channels = [...payload.channels];
  if (payload.recipient_roles) {
    body.recipient_roles = { ...payload.recipient_roles };
  }
  if (payload.thresholds) body.thresholds = { ...payload.thresholds };

  const response = await apiClient.patch(
    apiEndpoints.notificationAlerts.catalogByName(name),
    body,
  );
  const parsed = catalogUpdateResponseSchema.parse(response.data);
  return fromApiItem(parsed.data);
}

/** Catalog service — GET/PATCH `/api/v1/notification-alerts/catalog`. */
export const notificationAlertsService = {
  async listCatalog(
    type: NotificationAlertType,
    signal?: AbortSignal,
  ): Promise<NotificationAlertCatalogItem[]> {
    return listCatalogApi(type, signal);
  },

  async updateCatalog(
    name: string,
    payload: CatalogUpdatePayload,
  ): Promise<NotificationAlertCatalogItem> {
    return updateCatalogApi(name, payload);
  },
};
