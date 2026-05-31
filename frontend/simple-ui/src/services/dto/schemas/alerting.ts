import { z } from 'zod';

const alertAnnotationSchema = z.object({
  key: z.string(),
  value: z.string(),
});

/** Platform-core success envelope for all alert-management endpoints. */
export const alertSuccessEnvelopeSchema = <T extends z.ZodTypeAny>(dataSchema: T) =>
  z.object({
    success: z.boolean(),
    data: dataSchema,
    meta: z.record(z.unknown()).optional(),
  });

export const alertDefinitionSchema = z
  .object({
    id: z.number(),
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
    annotations: z.array(alertAnnotationSchema),
  })
  .passthrough();

export const notificationReceiverSchema = z
  .object({
    id: z.number(),
    receiver_name: z.string(),
    rule_name: z.string().nullable(),
    description: z.string().nullable(),
    category: z.string().nullable().optional(),
    severity: z.string().nullable().optional(),
    alert_names: z.array(z.string()).nullable(),
    tenant: z.string().nullable(),
    email_to: z.array(z.string()),
    rbac_role: z.string().nullable(),
    email_subject_template: z.string().nullable(),
    email_body_template: z.string().nullable(),
    enabled: z.boolean(),
    created_at: z.string(),
    updated_at: z.string(),
  })
  .passthrough();

export const routingRuleSchema = z
  .object({
    id: z.number(),
    rule_name: z.string(),
    receiver_id: z.number(),
    match_severity: z.string().nullable(),
    match_category: z.string().nullable(),
    match_alert_type: z.string().nullable(),
    match_alert_names: z.array(z.string()).nullable().optional(),
    match_tenant_id: z.string().nullable().optional(),
    group_by: z.array(z.string()),
    group_wait: z.string(),
    group_interval: z.string(),
    repeat_interval: z.string(),
    continue_routing: z.boolean(),
    priority: z.number(),
    enabled: z.boolean(),
    created_at: z.string(),
    updated_at: z.string(),
  })
  .passthrough();

export const alertHistoryItemSchema = z
  .object({
    id: z.number(),
    alert_name: z.string(),
    category: z.string(),
    severity: z.string(),
    triggered_at: z.string(),
    resolved_at: z.string().nullable().optional(),
    status: z.string(),
    receiver: z.string(),
    notified_display: z.string().nullable().optional(),
    tenant: z.string().nullable().optional(),
    labels: z.record(z.unknown()).nullable().optional(),
    annotations: z.record(z.unknown()).nullable().optional(),
    fingerprint: z.string().nullable().optional(),
    created_at: z.string(),
  })
  .passthrough();

export const alertHistoryListResponseSchema = z.object({
  items: z.array(alertHistoryItemSchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
});

export const deleteIdSchema = z.object({
  id: z.number(),
});

export const routingRuleTimingPatchResponseSchema = z.object({
  affected: z.number(),
});
