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
  created_by: string;
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
  organization: string;
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
  created_by: string | null;
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

// ---- Alert history (read-only audit log) ----

export interface AlertHistoryItem {
  id: number;
  name: string;
  category: string;
  severity: string;
  triggered_at: string | null;
  resolved_at: string | null;
  status: string;
  receiver: string | null;
  notified: string;
  tenant: string | null;
  organization: string | null;
  created_at: string | null;
}

export interface AlertHistoryListResponse {
  items: AlertHistoryItem[];
  total: number;
  limit: number;
  offset: number;
}

// ---- Allowed values ----

export const ORGANIZATIONS = ["irctc", "kisanmitra", "bashadaan", "beml"] as const;
export const CATEGORIES = ["application", "infrastructure"] as const;
export const SEVERITIES = ["critical", "warning", "info"] as const;
export const URGENCIES = ["high", "medium", "low"] as const;
export const RBAC_ROLES = ["ADMIN", "MODERATOR", "USER", "GUEST"] as const;
export const DEFAULT_GROUP_BY = ["alertname", "category", "severity", "organization"] as const;

// Create Alert Definition form options — strict hierarchy per API spec

/** category → allowed subcategories */
export const SUB_CATEGORIES_BY_CATEGORY: Record<string, { value: string; label: string }[]> = {
  application: [
    { value: "performance", label: "Performance" },
    { value: "availability", label: "Availability" },
  ],
  infrastructure: [
    { value: "compute", label: "Compute" },
    { value: "storage", label: "Storage" },
  ],
};

/** sub_category → allowed signals */
export const SIGNALS_BY_SUB_CATEGORY: Record<string, { value: string; label: string }[]> = {
  performance: [{ value: "latency", label: "Latency" }],
  availability: [{ value: "error_rate", label: "Error Rate" }],
  compute: [
    { value: "cpu_utilization", label: "CPU Utilization" },
    { value: "memory_utilization", label: "Memory Utilization" },
  ],
  storage: [{ value: "disk_utilization", label: "Disk Utilization" }],
};

/** signal → allowed signal_metrics */
export const SIGNAL_METRICS_BY_SIGNAL: Record<string, { value: string; label: string }[]> = {
  latency: [
    { value: "latency_p50", label: "Latency P50" },
    { value: "latency_p99", label: "Latency P99" },
  ],
  error_rate: [
    { value: "error_rate_4xx", label: "4xx Error Rate" },
    { value: "error_rate_5xx", label: "5xx Error Rate" },
    { value: "error_rate_timeout", label: "Timeout Error Rate" },
  ],
  cpu_utilization: [{ value: "total_cpu_usage", label: "Total CPU Usage" }],
  memory_utilization: [{ value: "total_memory_usage", label: "Total Memory Usage" }],
  disk_utilization: [{ value: "total_disk_usage", label: "Total Disk Usage" }],
};

/** All 11 application services (not used for infrastructure — always all) */
export const TARGET_SERVICES: { value: string; label: string }[] = [
  { value: "asr", label: "ASR (Automatic Speech Recognition)" },
  { value: "nmt", label: "NMT (Neural Machine Translation)" },
  { value: "tts", label: "TTS (Text-to-Speech)" },
  { value: "llm", label: "LLM (Large Language Model)" },
  { value: "audio-language-detection", label: "Audio Language Detection" },
  { value: "language-detection", label: "Language Detection" },
  { value: "language-diarization", label: "Language Diarization" },
  { value: "speaker-diarization", label: "Speaker Diarization" },
  { value: "ocr", label: "OCR (Optical Character Recognition)" },
  { value: "transliteration", label: "Transliteration" },
  { value: "ner", label: "NER (Named Entity Recognition)" },
];

export const CONDITION_OPERATORS: { value: string; label: string }[] = [
  { value: "<", label: "<" },
  { value: "<=", label: "<=" },
  { value: ">", label: ">" },
  { value: ">=", label: ">=" },
];

/** Only for latency signal — user can pick ms or s */
export const LATENCY_THRESHOLD_UNITS: { value: string; label: string }[] = [
  { value: "ms", label: "ms" },
  { value: "s", label: "s" },
];

/** For all non-latency signals — always percentage, no choice */
export const PERCENTAGE_UNIT = "%";

export const THRESHOLD_UNITS: { value: string; label: string }[] = [
  { value: "ms", label: "ms" },
  { value: "s", label: "s" },
  { value: "%", label: "%" },
];
