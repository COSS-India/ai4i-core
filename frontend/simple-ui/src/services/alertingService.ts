/**
 * Alerting service — Alert Definitions, Receivers, Routing Rules, and read-only Alert History.
 * Follows the same request pattern as authService (fetch + Bearer token).
 */
import type { ZodTypeAny } from 'zod';
import { z } from 'zod';
import { getApiBaseUrl, apiService } from './api';
import {
  alertDefinitionSchema,
  alertHistoryItemSchema,
  alertSuccessEnvelopeSchema,
  deleteIdSchema,
  notificationReceiverSchema,
  routingRuleSchema,
  routingRuleTimingPatchResponseSchema,
} from './dto/schemas/alerting';
import { ApiValidationError } from './dto/apiValidationError';
import { apiEndpoints } from './apiEndpoints';
import authService from './authService';

const alertPath = apiEndpoints.alerts.paths;
import type {
  AlertDefinition,
  AlertDefinitionCreate,
  AlertDefinitionUpdate,
  AlertHistoryListResponse,
  NotificationReceiver,
  NotificationReceiverCreate,
  NotificationReceiverUpdate,
  RoutingRule,
  RoutingRuleCreate,
  RoutingRuleUpdate,
  RoutingRuleTimingUpdate,
} from '../types/alerting';

class AlertingService {
  private get baseUrl(): string {
    return `${getApiBaseUrl()}${apiEndpoints.alerts.base}`;
  }

  private getAccessToken(): string | null {
    return authService.getAccessToken();
  }

  private async request<S extends ZodTypeAny>(
    endpoint: string,
    schema: S,
    options: RequestInit = {}
  ): Promise<z.infer<S>> {
    const url = `${this.baseUrl}${endpoint}`;

    const defaultHeaders: HeadersInit = {
      'Content-Type': 'application/json',
    };

    const token = this.getAccessToken();
    if (token) {
      defaultHeaders.Authorization = `Bearer ${token}`;
    }

    const config: RequestInit = {
      ...options,
      headers: {
        ...defaultHeaders,
        ...options.headers,
      },
    };

    const timeoutMs = 15000;

    try {
      const response = await apiService.request(
        (config.method || 'GET') as any,
        url,
        config.body,
        {
          headers: config.headers as Record<string, string>,
          timeout: timeoutMs,
          responseSchema: alertSuccessEnvelopeSchema(schema),
        }
      );
      return response.data.data as z.infer<S>;
    } catch (error: any) {
      if (error?.code === 'ECONNABORTED') {
        throw new Error('Request timeout: Alerting service is not responding');
      }
      if (error instanceof ApiValidationError) {
        throw error;
      }
      const status = error?.response?.status;
      const errorData = error?.response?.data ?? {};
      let errorMessage = status ? `HTTP error! status: ${status}` : 'Request failed';
      if (errorData?.detail) {
        const d = errorData.detail;
        if (typeof d === 'string') {
          errorMessage = d;
        } else if (typeof d === 'object' && d !== null) {
          errorMessage =
            (d as any).message != null
              ? String((d as any).message)
              : JSON.stringify(d);
        }
      } else if (errorData?.message) {
        errorMessage = String(errorData.message);
      } else if (errorData?.error?.message) {
        errorMessage = String(errorData.error.message);
      } else if (error?.message) {
        errorMessage = String(error.message);
      }
      const normalizedError = new Error(errorMessage);
      (normalizedError as any).status = status;
      throw normalizedError;
    }
  }

  // ---- Alert Definitions ----

  async listDefinitions(enabledOnly?: boolean): Promise<AlertDefinition[]> {
    const params = enabledOnly ? '?enabled_only=true' : '';
    return this.request(`${alertPath.definitions}${params}`, z.array(alertDefinitionSchema), {
      method: 'GET',
    });
  }

  async getDefinition(alertId: number): Promise<AlertDefinition> {
    return this.request(alertPath.definition(alertId), alertDefinitionSchema, { method: 'GET' });
  }

  async createDefinition(
    data: AlertDefinitionCreate
  ): Promise<AlertDefinition> {
    const body: Record<string, unknown> = {
      name: data.name,
      description: data.description ?? null,
      category: data.category ?? 'application',
      severity: data.severity,
      urgency: data.urgency ?? 'medium',
      sub_category: data.sub_category ?? null,
      signal: data.signal ?? null,
      signal_metric: data.signal_metric ?? null,
      condition_operator: data.condition_operator ?? null,
      threshold_value: data.threshold_value,
      threshold_unit: (data.threshold_unit ?? 's').trim(),
      service: data.service && data.service.length > 0 ? data.service : undefined,
      evaluation_interval: data.evaluation_interval ?? '30s',
      for_duration: data.for_duration ?? '1m',
      enabled: data.enabled !== false,
      annotations: data.annotations,
    };
    return this.request(alertPath.definitions, alertDefinitionSchema, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async updateDefinition(
    alertId: number,
    data: AlertDefinitionUpdate
  ): Promise<AlertDefinition> {
    return this.request(alertPath.definition(alertId), alertDefinitionSchema, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async toggleDefinitionEnabled(
    alertId: number,
    enabled: boolean
  ): Promise<AlertDefinition> {
    return this.request(alertPath.definitionEnabled(alertId), alertDefinitionSchema, {
      method: 'PATCH',
      body: JSON.stringify({ enabled }),
    });
  }

  async deleteDefinition(alertId: number): Promise<{ id: number }> {
    return this.request(alertPath.definition(alertId), deleteIdSchema, {
      method: 'DELETE',
    });
  }

  // ---- Notification Receivers ----

  async listReceivers(enabledOnly?: boolean): Promise<NotificationReceiver[]> {
    const params = enabledOnly ? '?enabled_only=true' : '';
    return this.request(`${alertPath.receivers}${params}`, z.array(notificationReceiverSchema), {
      method: 'GET',
    });
  }

  async getReceiver(receiverId: number): Promise<NotificationReceiver> {
    return this.request(alertPath.receiver(receiverId), notificationReceiverSchema, {
      method: 'GET',
    });
  }

  async createReceiver(
    data: NotificationReceiverCreate
  ): Promise<NotificationReceiver> {
    return this.request(alertPath.receivers, notificationReceiverSchema, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateReceiver(
    receiverId: number,
    data: NotificationReceiverUpdate
  ): Promise<NotificationReceiver> {
    return this.request(alertPath.receiver(receiverId), notificationReceiverSchema, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteReceiver(receiverId: number): Promise<{ id: number }> {
    return this.request(alertPath.receiver(receiverId), deleteIdSchema, {
      method: 'DELETE',
    });
  }

  // ---- Routing Rules ----

  async listRoutingRules(enabledOnly?: boolean): Promise<RoutingRule[]> {
    const params = enabledOnly ? '?enabled_only=true' : '';
    return this.request(`${alertPath.routingRules}${params}`, z.array(routingRuleSchema), {
      method: 'GET',
    });
  }

  async getRoutingRule(ruleId: number): Promise<RoutingRule> {
    return this.request(alertPath.routingRule(ruleId), routingRuleSchema, { method: 'GET' });
  }

  async createRoutingRule(data: RoutingRuleCreate): Promise<RoutingRule> {
    return this.request(alertPath.routingRules, routingRuleSchema, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateRoutingRule(
    ruleId: number,
    data: RoutingRuleUpdate
  ): Promise<RoutingRule> {
    return this.request(alertPath.routingRule(ruleId), routingRuleSchema, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteRoutingRule(ruleId: number): Promise<{ id: number }> {
    return this.request(alertPath.routingRule(ruleId), deleteIdSchema, {
      method: 'DELETE',
    });
  }

  async bulkUpdateRoutingRuleTiming(
    data: RoutingRuleTimingUpdate
  ): Promise<{ affected: number }> {
    return this.request(alertPath.routingRulesTiming, routingRuleTimingPatchResponseSchema, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  // ---- Alert history (read-only) ----

  async listAlertHistory(params?: {
    category?: string;
    severity?: string;
    date_from?: string;
    date_to?: string;
    search?: string;
    limit?: number;
    offset?: number;
  }): Promise<AlertHistoryListResponse> {
    const q = new URLSearchParams();
    if (params?.category) q.set('category', params.category);
    if (params?.severity) q.set('severity', params.severity);
    if (params?.date_from) q.set('date_from', params.date_from);
    if (params?.date_to) q.set('date_to', params.date_to);
    if (params?.search) q.set('search', params.search);
    if (params?.limit != null) q.set('limit', String(params.limit));
    if (params?.offset != null) q.set('offset', String(params.offset));
    const qs = q.toString();
    const endpoint = qs ? `${alertPath.history}?${qs}` : alertPath.history;
    const url = `${this.baseUrl}${endpoint}`;

    const defaultHeaders: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    const token = this.getAccessToken();
    if (token) {
      defaultHeaders.Authorization = `Bearer ${token}`;
    }

    try {
      const response = await apiService.request(
        'GET',
        url,
        undefined,
        {
          headers: defaultHeaders,
          timeout: 15000,
          responseSchema: alertSuccessEnvelopeSchema(z.array(alertHistoryItemSchema)),
        }
      );
      const envelope = response.data;
      const meta = envelope.meta ?? {};
      const limit = params?.limit ?? 50;
      const offset = params?.offset ?? 0;
      return {
        items: envelope.data,
        total: typeof meta.total === 'number' ? meta.total : envelope.data.length,
        limit: typeof meta.limit === 'number' ? meta.limit : limit,
        offset: typeof meta.offset === 'number' ? meta.offset : offset,
      };
    } catch (error: any) {
      if (error instanceof ApiValidationError) {
        throw error;
      }
      const status = error?.response?.status;
      const errorData = error?.response?.data ?? {};
      let errorMessage = status ? `HTTP error! status: ${status}` : 'Request failed';
      if (errorData?.detail?.message) {
        errorMessage = String(errorData.detail.message);
      } else if (error?.message) {
        errorMessage = String(error.message);
      }
      throw new Error(errorMessage);
    }
  }
}

const alertingService = new AlertingService();
export default alertingService;
