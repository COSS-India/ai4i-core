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
  organization: string;
  name: string;
  description: string | null;
  promql_expr: string;
  threshold_value?: number | null;
  threshold_unit?: string | null;
  category: string;
  severity: string;
  urgency: string;
  alert_type: string | null;
  scope: string | null;
  evaluation_interval: string;
  for_duration: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  created_by: string;
  annotations: AlertAnnotation[];
}

export interface AlertDefinitionCreate {
  name: string;
  description?: string | null;
  promql_expr: string;
  category?: string;
  severity: string;
  urgency?: string;
  alert_type?: string | null;
  scope?: string | null;
  evaluation_interval?: string;
  for_duration?: string;
  annotations?: AlertAnnotation[];
}

export interface AlertDefinitionUpdate {
  description?: string | null;
  promql_expr?: string;
  category?: string;
  severity?: string;
  urgency?: string;
  alert_type?: string | null;
  scope?: string | null;
  evaluation_interval?: string;
  for_duration?: string;
  enabled?: boolean;
  annotations?: AlertAnnotation[];
}

// ---- Notification Receivers ----

export interface NotificationReceiver {
  id: number;
  organization: string;
  receiver_name: string;
  email_to: string[] | null;
  rbac_role: string | null;
  email_subject_template: string | null;
  email_body_template: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  created_by: string;
}

export interface NotificationReceiverCreate {
  category: string;
  severity: string;
  alert_type?: string | null;
  email_to?: string[];
  rbac_role?: string | null;
  email_subject_template?: string | null;
  email_body_template?: string | null;
}

export interface NotificationReceiverUpdate {
  receiver_name?: string;
  email_to?: string[];
  rbac_role?: string | null;
  email_subject_template?: string | null;
  email_body_template?: string | null;
  enabled?: boolean;
}

// ---- Routing Rules ----

export interface RoutingRule {
  id: number;
  organization: string;
  rule_name: string;
  receiver_id: number;
  match_severity: string | null;
  match_category: string | null;
  match_alert_type: string | null;
  group_by: string[];
  group_wait: string;
  group_interval: string;
  repeat_interval: string;
  continue_routing: boolean;
  priority: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  created_by: string;
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

// ---- Allowed values ----

export const ORGANIZATIONS = ["irctc", "kisanmitra", "bashadaan", "beml"] as const;
export const CATEGORIES = ["application", "infrastructure"] as const;
export const SEVERITIES = ["critical", "warning", "info"] as const;
export const URGENCIES = ["high", "medium", "low"] as const;
export const RBAC_ROLES = ["ADMIN", "MODERATOR", "USER", "GUEST"] as const;
export const DEFAULT_GROUP_BY = ["alertname", "category", "severity", "organization"] as const;
