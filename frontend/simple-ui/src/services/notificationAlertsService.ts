import apiClient from "./api";
import { apiEndpoints } from "./apiEndpoints";
import {
  catalogListResponseSchema,
  catalogUpdateResponseSchema,
  subscriptionListResponseSchema,
  subscriptionUpdateResponseSchema,
  type ApiCatalogItem,
  type ApiSubscriptionItem,
} from "./dto/schemas/notificationAlerts";
import type {
  CatalogUpdatePayload,
  NotificationAlertCatalogItem,
  NotificationAlertType,
  NotificationSubscriptionItem,
} from "../types/notificationAlerts";
import { normalizeRecipientRoles } from "../types/notificationAlerts";
import { replaceTenantCopy } from "../utils/replaceTenantCopy";

function fromApiItem(item: ApiCatalogItem): NotificationAlertCatalogItem {
  return {
    id: item.id,
    name: item.name,
    display_name: replaceTenantCopy(item.display_name),
    description: replaceTenantCopy(item.description),
    type: item.type,
    module: item.module,
    channels: [...item.channels],
    recipient_roles: normalizeRecipientRoles(item.recipient_roles),
    scope: item.scope,
    thresholds:
      item.thresholds == null
        ? undefined
        : item.thresholds.map((band) => ({ ...band })),
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
  if (payload.scope) body.scope = payload.scope;
  // Wholesale replacement — the BE has no per-band merge (percentage itself
  // is editable, so a band has no stable key to merge against).
  if (payload.thresholds) {
    body.thresholds = payload.thresholds.map((band) => ({ ...band }));
  }

  const response = await apiClient.patch(
    apiEndpoints.notificationAlerts.catalogByName(name),
    body,
  );
  const parsed = catalogUpdateResponseSchema.parse(response.data);
  return fromApiItem(parsed.data);
}

function fromApiSubscription(item: ApiSubscriptionItem): NotificationSubscriptionItem {
  return {
    notification_id: item.notification_id,
    name: item.name,
    display_name: replaceTenantCopy(item.display_name),
    description: replaceTenantCopy(item.description ?? ""),
    scope: item.scope,
    channels: [...item.delivery_channel],
    subscribed: item.subscribed,
    locked: item.locked,
    recipients: [...item.recipients],
    thresholds:
      item.thresholds == null
        ? undefined
        : item.thresholds.map((band) => ({ ...band })),
  };
}

async function listSubscriptionsApi(
  tenantId: string,
  type: NotificationAlertType,
  signal?: AbortSignal,
): Promise<NotificationSubscriptionItem[]> {
  const response = await apiClient.get(apiEndpoints.notificationAlerts.subscriptions, {
    params: { tenant_id: tenantId, type },
    signal,
  });
  const parsed = subscriptionListResponseSchema.parse(response.data);
  return parsed.data.items.map(fromApiSubscription);
}

async function updateSubscriptionStateApi(
  tenantId: string,
  notificationId: number,
  subscribed: boolean,
): Promise<NotificationSubscriptionItem> {
  const response = await apiClient.patch(
    apiEndpoints.notificationAlerts.subscriptionById(notificationId),
    { subscribed },
    { params: { tenant_id: tenantId } },
  );
  const parsed = subscriptionUpdateResponseSchema.parse(response.data);
  return fromApiSubscription(parsed.data);
}

async function updateSubscriptionRecipientsApi(
  tenantId: string,
  notificationId: number,
  recipients: string[],
): Promise<NotificationSubscriptionItem> {
  const response = await apiClient.put(
    apiEndpoints.notificationAlerts.subscriptionById(notificationId),
    { recipients: [...recipients] },
    { params: { tenant_id: tenantId } },
  );
  const parsed = subscriptionUpdateResponseSchema.parse(response.data);
  return fromApiSubscription(parsed.data);
}

/**
 * Catalog service — GET/PATCH `/api/v1/notification-alerts/catalog` (Adopter
 * Admin) and GET/PATCH/PUT `/api/v1/notification-alerts/subscriptions`
 * (Institution Admin).
 */
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

  async listSubscriptions(
    tenantId: string,
    type: NotificationAlertType,
    signal?: AbortSignal,
  ): Promise<NotificationSubscriptionItem[]> {
    return listSubscriptionsApi(tenantId, type, signal);
  },

  /** 409 on a locked (GLOBAL) row — callers must not send those. */
  async updateSubscriptionState(
    tenantId: string,
    notificationId: number,
    subscribed: boolean,
  ): Promise<NotificationSubscriptionItem> {
    return updateSubscriptionStateApi(tenantId, notificationId, subscribed);
  },

  /** Wholesale replacement of the row's additional recipients. */
  async updateSubscriptionRecipients(
    tenantId: string,
    notificationId: number,
    recipients: string[],
  ): Promise<NotificationSubscriptionItem> {
    return updateSubscriptionRecipientsApi(tenantId, notificationId, recipients);
  },
};
