import { z } from 'zod';

const alertAnnotationSchema = z.object({
  key: z.string(),
  value: z.string(),
});

export const alertDefinitionSchema = z
  .object({
    id: z.number(),
    organization: z.string(),
    name: z.string(),
    description: z.string().nullable(),
    promql_expr: z.string(),
    threshold_value: z.number().nullable().optional(),
    threshold_unit: z.string().nullable().optional(),
    category: z.string(),
    severity: z.string(),
    urgency: z.string(),
    alert_type: z.string().nullable(),
    sub_category: z.string().nullable().optional(),
    signal: z.string().nullable().optional(),
    signal_metric: z.string().nullable().optional(),
    condition_operator: z.string().nullable().optional(),
    scope: z.string().nullable(),
    service: z.array(z.string()).nullable().optional(),
    evaluation_interval: z.string(),
    for_duration: z.string(),
    enabled: z.boolean(),
    created_at: z.string(),
    updated_at: z.string(),
    created_by: z.string(),
    annotations: z.array(alertAnnotationSchema),
  })
  .passthrough();

export const notificationReceiverSchema = z
  .object({
    id: z.number(),
    organization: z.string(),
    receiver_name: z.string(),
    rule_name: z.string().nullable(),
    description: z.string().nullable(),
    category: z.string().nullable().optional(),
    severity: z.string().nullable().optional(),
    alert_type: z.string().nullable().optional(),
    alert_names: z.array(z.string()).nullable(),
    tenant: z.string().nullable(),
    email_to: z.array(z.string()),
    rbac_role: z.string().nullable(),
    email_subject_template: z.string().nullable(),
    email_body_template: z.string().nullable(),
    enabled: z.boolean(),
    created_at: z.string(),
    updated_at: z.string(),
    created_by: z.string().nullable(),
  })
  .passthrough();

export const routingRuleSchema = z
  .object({
    id: z.number(),
    organization: z.string(),
    rule_name: z.string(),
    receiver_id: z.number(),
    match_severity: z.string().nullable(),
    match_category: z.string().nullable(),
    match_alert_type: z.string().nullable(),
    group_by: z.array(z.string()),
    group_wait: z.string(),
    group_interval: z.string(),
    repeat_interval: z.string(),
    continue_routing: z.boolean(),
    priority: z.number(),
    enabled: z.boolean(),
    created_at: z.string(),
    updated_at: z.string(),
    created_by: z.string(),
  })
  .passthrough();

export const alertHistoryItemSchema = z
  .object({
    id: z.number(),
    name: z.string(),
    category: z.string(),
    severity: z.string(),
    triggered_at: z.string().nullable(),
    resolved_at: z.string().nullable(),
    status: z.string(),
    receiver: z.string().nullable(),
    notified: z.string(),
    tenant: z.string().nullable(),
    organization: z.string().nullable(),
    created_at: z.string().nullable(),
  })
  .passthrough();

export const alertHistoryListResponseSchema = z.object({
  items: z.array(alertHistoryItemSchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
});

export const deleteMessageSchema = z.object({
  message: z.string(),
});

export const routingRuleTimingPatchResponseSchema = z.record(z.unknown());
