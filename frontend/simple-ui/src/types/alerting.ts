/**
 * Alerting types for Alert Definitions, Notification Receivers, and Routing Rules
 */

// ---- Common ----

export interface AlertAnnotation {
  key: string;
  value: string;
}

// ---- Alert Definitions ----

export interface AlertDefinition {
  id: number;
  name: string;
  description: string | null;
  promql_expr: string;
  threshold_value?: number | null;
  threshold_unit?: string | null;
  category: string;
  severity: string;
  urgency: string;
  alert_type: string | null;
  sub_category?: string | null;
  signal?: string | null;
  signal_metric?: string | null;
  condition_operator?: string | null;
  scope: string | null;
  service?: string[] | null;
  evaluation_interval: string;
  for_duration: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  annotations: AlertAnnotation[];
}

export interface AlertDefinitionCreate {
  name: string;
  description?: string | null;
  category?: string;
  severity: string;
  urgency?: string;
  sub_category?: string | null;
  signal?: string | null;
  signal_metric?: string | null;
  condition_operator?: string | null;
  threshold_value?: number | null;
  threshold_unit?: string | null;
  scope?: string | null;
  service?: string[] | null;
  evaluation_interval?: string;
  for_duration?: string;
  enabled?: boolean;
  annotations?: AlertAnnotation[];
}

export interface AlertDefinitionUpdate {
  description?: string | null;
  category?: string;
  severity?: string;
  urgency?: string;
  sub_category?: string | null;
  signal?: string | null;
  signal_metric?: string | null;
  condition_operator?: string | null;
  threshold_value?: number | null;
  threshold_unit?: string | null;
  scope?: string | null;
  service?: string[] | null;
  evaluation_interval?: string;
  for_duration?: string;
  enabled?: boolean;
  annotations?: AlertAnnotation[];
}

// ---- Notification Receivers ----

export interface NotificationReceiver {
  id: number;
  receiver_name: string;
  rule_name: string | null;
  description: string | null;
  category?: string | null;
  severity?: string | null;
  alert_type?: string | null;
  alert_names: string[] | null;
  tenant: string | null;
  email_to: string[];
  rbac_role: string | null;
  email_subject_template: string | null;
  email_body_template: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface NotificationReceiverCreate {
  category: string;
  severity: string;
  alert_type?: string | null;
  alert_names?: string[] | null;
  tenant?: string | null;
  rule_name?: string | null;
  description?: string | null;
  email_to?: string[];
  rbac_role?: string | null;
  email_subject_template?: string | null;
  email_body_template?: string | null;
}

export interface NotificationReceiverUpdate {
  rule_name?: string | null;
  description?: string | null;
  category?: string | null;
  severity?: string | null;
  alert_type?: string | null;
  alert_names?: string[] | null;
  tenant?: string | null;
  email_to?: string[];
  rbac_role?: string | null;
  email_subject_template?: string | null;
  email_body_template?: string | null;
  enabled?: boolean;
}

// ---- Routing Rules ----

export interface RoutingRule {
  id: number;
  rule_name: string;
  receiver_id: number;
  match_severity: string | null;
  match_category: string | null;
  match_alert_type: string | null;
  match_alert_names?: string[] | null;
  match_tenant_id?: string | null;
  group_by: string[];
  group_wait: string;
  group_interval: string;
  repeat_interval: string;
  continue_routing: boolean;
  priority: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface RoutingRuleCreate {
  rule_name: string;
  receiver_id: number;
  match_severity?: string | null;
  match_category?: string | null;
  match_alert_type?: string | null;
  group_by?: string[];
  group_wait?: string;
  group_interval?: string;
  repeat_interval?: string;
  continue_routing?: boolean;
  priority?: number;
}

export interface RoutingRuleUpdate {
  rule_name?: string;
  receiver_id?: number;
  match_severity?: string | null;
  match_category?: string | null;
  match_alert_type?: string | null;
  group_by?: string[];
  group_wait?: string;
  group_interval?: string;
  repeat_interval?: string;
  continue_routing?: boolean;
  priority?: number;
  enabled?: boolean;
}

export interface RoutingRuleTimingUpdate {
  category: string;
  severity: string;
  alert_type?: string | null;
  priority?: number | null;
  group_wait?: string | null;
  group_interval?: string | null;
  repeat_interval?: string | null;
}

// ---- Alert history (read-only audit log) ----

export interface AlertHistoryItem {
  id: number;
  alert_name: string;
  category: string;
  severity: string;
  triggered_at: string;
  resolved_at?: string | null;
  status: string;
  receiver: string;
  notified_display?: string | null;
  tenant?: string | null;
  labels?: Record<string, unknown> | null;
  annotations?: Record<string, unknown> | null;
  fingerprint?: string | null;
  created_at: string;
}

export interface AlertHistoryListResponse {
  items: AlertHistoryItem[];
  total: number;
  limit: number;
  offset: number;
}
