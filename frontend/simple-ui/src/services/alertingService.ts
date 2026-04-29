/**
 * Alerting service — Alert Definitions, Receivers, Routing Rules, and read-only Alert History.
 * Follows the same request pattern as authService.
 */
import axios from 'axios';
import { apiClient, apiEndpoints } from './api';
import authService from './authService';
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

const alertPaths = apiEndpoints.alerts.paths;

class AlertingService {
  private getAccessToken(): string | null {
    return authService.getAccessToken();
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${apiEndpoints.alerts.base}${endpoint}`;

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

    const method = (options.method || 'GET') as 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
    const requestData =
      typeof options.body === 'string' ? JSON.parse(options.body) : options.body;

    try {
      const response = await apiClient.request<T>({
        url,
        method,
        data: requestData,
        headers: config.headers as Record<string, string>,
        timeout: 15000,
      });
      const payload = response.data as any;
      if (payload && typeof payload === 'object' && 'success' in payload && 'data' in payload) {
        return payload.data as T;
      }
      return payload as T;
    } catch (error: any) {
      if (axios.isAxiosError(error)) {
        if (error.code === 'ECONNABORTED') {
          throw new Error('Request timeout: Alerting service is not responding');
        }

        const status = error.response?.status;
        const errorData: any = error.response?.data ?? {};
        let errorMessage = `HTTP error! status: ${status ?? 'unknown'}`;
        if (errorData?.detail) {
          const d = errorData.detail;
          if (typeof d === 'string') {
            errorMessage = d;
          } else if (typeof d === 'object' && d !== null) {
            errorMessage = (d as any).message != null ? String((d as any).message) : JSON.stringify(d);
          }
        } else if (errorData?.message) {
          errorMessage = String(errorData.message);
        } else if (error.message) {
          errorMessage = error.message;
        }

        const mappedError = new Error(errorMessage);
        (mappedError as any).status = status;
        throw mappedError;
      }

      if (error?.name === 'AbortError') {
        throw new Error('Request timeout: Alerting service is not responding');
      }
      throw error;
    }
  }

  // ---- Alert Definitions ----

  async listDefinitions(enabledOnly?: boolean): Promise<AlertDefinition[]> {
    const params = enabledOnly ? '?enabled_only=true' : '';
    return this.request<AlertDefinition[]>(`${alertPaths.definitions}${params}`);
  }

  async getDefinition(alertId: number): Promise<AlertDefinition> {
    return this.request<AlertDefinition>(`${alertPaths.definitions}/${alertId}`);
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
    return this.request<AlertDefinition>(alertPaths.definitions, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async updateDefinition(
    alertId: number,
    data: AlertDefinitionUpdate
  ): Promise<AlertDefinition> {
    return this.request<AlertDefinition>(`${alertPaths.definitions}/${alertId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async toggleDefinitionEnabled(
    alertId: number,
    enabled: boolean
  ): Promise<AlertDefinition> {
    return this.request<AlertDefinition>(
      `${alertPaths.definitions}/${alertId}/enabled`,
      {
      method: 'PATCH',
      body: JSON.stringify({ enabled }),
      }
    );
  }

  async deleteDefinition(alertId: number): Promise<{ message: string }> {
    return this.request<{ message: string }>(`${alertPaths.definitions}/${alertId}`, {
      method: 'DELETE',
    });
  }

  // ---- Notification Receivers ----

  async listReceivers(enabledOnly?: boolean): Promise<NotificationReceiver[]> {
    const params = enabledOnly ? '?enabled_only=true' : '';
    return this.request<NotificationReceiver[]>(`${alertPaths.receivers}${params}`);
  }

  async getReceiver(receiverId: number): Promise<NotificationReceiver> {
    return this.request<NotificationReceiver>(`${alertPaths.receivers}/${receiverId}`);
  }

  async createReceiver(
    data: NotificationReceiverCreate
  ): Promise<NotificationReceiver> {
    return this.request<NotificationReceiver>(alertPaths.receivers, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateReceiver(
    receiverId: number,
    data: NotificationReceiverUpdate
  ): Promise<NotificationReceiver> {
    return this.request<NotificationReceiver>(`${alertPaths.receivers}/${receiverId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteReceiver(receiverId: number): Promise<{ message: string }> {
    return this.request<{ message: string }>(`${alertPaths.receivers}/${receiverId}`, {
      method: 'DELETE',
    });
  }

  // ---- Routing Rules ----

  async listRoutingRules(enabledOnly?: boolean): Promise<RoutingRule[]> {
    const params = enabledOnly ? '?enabled_only=true' : '';
    return this.request<RoutingRule[]>(`${alertPaths.routingRules}${params}`);
  }

  async getRoutingRule(ruleId: number): Promise<RoutingRule> {
    return this.request<RoutingRule>(`${alertPaths.routingRules}/${ruleId}`);
  }

  async createRoutingRule(data: RoutingRuleCreate): Promise<RoutingRule> {
    return this.request<RoutingRule>(alertPaths.routingRules, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateRoutingRule(
    ruleId: number,
    data: RoutingRuleUpdate
  ): Promise<RoutingRule> {
    return this.request<RoutingRule>(`${alertPaths.routingRules}/${ruleId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteRoutingRule(ruleId: number): Promise<{ message: string }> {
    return this.request<{ message: string }>(
      `${alertPaths.routingRules}/${ruleId}`,
      {
      method: 'DELETE',
      }
    );
  }

  async bulkUpdateRoutingRuleTiming(
    data: RoutingRuleTimingUpdate
  ): Promise<any> {
    return this.request<any>(alertPaths.routingRulesTiming, {
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
    const historyPath = alertPaths.history;
    return this.request<AlertHistoryListResponse>(
      qs ? `${historyPath}?${qs}` : historyPath
    );
  }
}

const alertingService = new AlertingService();
export default alertingService;
