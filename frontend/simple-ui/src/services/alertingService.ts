/**
 * Alerting service — handles Alert Definitions, Notification Receivers, and Routing Rules.
 * Follows the same request pattern as authService (fetch + Bearer token).
 */
import { API_BASE_URL } from './api';
import type {
  AlertDefinition,
  AlertDefinitionCreate,
  AlertDefinitionUpdate,
  NotificationReceiver,
  NotificationReceiverCreate,
  NotificationReceiverUpdate,
  RoutingRule,
  RoutingRuleCreate,
  RoutingRuleUpdate,
  RoutingRuleTimingUpdate,
} from '../types/alerting';

class AlertingService {
  private baseUrl: string;

  constructor() {
    this.baseUrl = `${API_BASE_URL}/api/v1/alerts`;
  }

  private getAccessToken(): string | null {
    if (typeof window !== 'undefined') {
      return (
        localStorage.getItem('access_token') ||
        sessionStorage.getItem('access_token')
      );
    }
    return null;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
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
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(url, {
        ...config,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (!response.ok) {
        let errorData: any = {};
        try {
          const text = await response.text();
          if (text) {
            errorData = JSON.parse(text);
          }
        } catch {
          errorData = {};
        }

        let errorMessage = `HTTP error! status: ${response.status}`;
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
        }

        const error = new Error(errorMessage);
        (error as any).status = response.status;
        throw error;
      }

      return await response.json();
    } catch (error: any) {
      clearTimeout(timeoutId);
      if (error.name === 'AbortError') {
        throw new Error('Request timeout: Alerting service is not responding');
      }
      throw error;
    }
  }

  // ---- Alert Definitions ----

  async listDefinitions(enabledOnly?: boolean): Promise<AlertDefinition[]> {
    const params = enabledOnly ? '?enabled_only=true' : '';
    return this.request<AlertDefinition[]>(`/definitions${params}`);
  }

  async getDefinition(alertId: number): Promise<AlertDefinition> {
    return this.request<AlertDefinition>(`/definitions/${alertId}`);
  }

  async createDefinition(
    data: AlertDefinitionCreate
  ): Promise<AlertDefinition> {
    return this.request<AlertDefinition>('/definitions', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateDefinition(
    alertId: number,
    data: AlertDefinitionUpdate
  ): Promise<AlertDefinition> {
    return this.request<AlertDefinition>(`/definitions/${alertId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async toggleDefinitionEnabled(
    alertId: number,
    enabled: boolean
  ): Promise<AlertDefinition> {
    return this.request<AlertDefinition>(`/definitions/${alertId}/enabled`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled }),
    });
  }

  async deleteDefinition(alertId: number): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/definitions/${alertId}`, {
      method: 'DELETE',
    });
  }

  // ---- Notification Receivers ----

  async listReceivers(enabledOnly?: boolean): Promise<NotificationReceiver[]> {
    const params = enabledOnly ? '?enabled_only=true' : '';
    return this.request<NotificationReceiver[]>(`/receivers${params}`);
  }

  async getReceiver(receiverId: number): Promise<NotificationReceiver> {
    return this.request<NotificationReceiver>(`/receivers/${receiverId}`);
  }

  async createReceiver(
    data: NotificationReceiverCreate
  ): Promise<NotificationReceiver> {
    return this.request<NotificationReceiver>('/receivers', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateReceiver(
    receiverId: number,
    data: NotificationReceiverUpdate
  ): Promise<NotificationReceiver> {
    return this.request<NotificationReceiver>(`/receivers/${receiverId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteReceiver(receiverId: number): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/receivers/${receiverId}`, {
      method: 'DELETE',
    });
  }

  // ---- Routing Rules ----

  async listRoutingRules(enabledOnly?: boolean): Promise<RoutingRule[]> {
    const params = enabledOnly ? '?enabled_only=true' : '';
    return this.request<RoutingRule[]>(`/routing-rules${params}`);
  }

  async getRoutingRule(ruleId: number): Promise<RoutingRule> {
    return this.request<RoutingRule>(`/routing-rules/${ruleId}`);
  }

  async createRoutingRule(data: RoutingRuleCreate): Promise<RoutingRule> {
    return this.request<RoutingRule>('/routing-rules', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateRoutingRule(
    ruleId: number,
    data: RoutingRuleUpdate
  ): Promise<RoutingRule> {
    return this.request<RoutingRule>(`/routing-rules/${ruleId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteRoutingRule(ruleId: number): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/routing-rules/${ruleId}`, {
      method: 'DELETE',
    });
  }

  async bulkUpdateRoutingRuleTiming(
    data: RoutingRuleTimingUpdate
  ): Promise<any> {
    return this.request<any>('/routing-rules/timing', {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }
}

const alertingService = new AlertingService();
export default alertingService;
