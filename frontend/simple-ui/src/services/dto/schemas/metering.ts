import { z } from "zod";

export const meteringPeriodSchema = z.object({
  key: z.enum(["today", "yesterday", "last_7_days", "custom"]),
  from: z.string(),
  to: z.string(),
  start: z.string(),
  end: z.string(),
  timezone: z.string(),
});

export const meteringCellSchema = z.object({
  key: z.string(),
  label: z.string(),
  value: z.union([z.string(), z.number(), z.null()]),
  previous: z.union([z.string(), z.number(), z.null()]).optional(),
  pct_change: z.number().nullable().optional(),
  helper: z.string().nullable().optional(),
});

export const meteringGraphPointSchema = z.object({
  ts: z.number(),
  value: z.number(),
});

export const meteringGraphSeriesSchema = z.object({
  key: z.string(),
  label: z.string(),
  points: z.array(meteringGraphPointSchema),
});

export const meteringGraphSchema = z.object({
  step: z.enum(["1h", "1d", "1w"]).optional(),
  series: z.array(meteringGraphSeriesSchema),
});

export const meteringScopeSchema = z.object({
  role: z.string(),
  tenant_id: z.string().nullable(),
  organisation: z.string().nullable(),
  period: meteringPeriodSchema,
  task_types: z.array(z.string()).nullable().optional(),
});

export const platformAdoptionSchema = z.object({
  total_tenants: z.number().nullable().optional(),
  new_tenants_15d: z.number().nullable().optional(),
  active_24h: z.number().nullable().optional(),
  active_7d: z.number().nullable().optional(),
  active_30d: z.number().nullable().optional(),
  model_usage_growth_pct: z.number().nullable().optional(),
  total_models: z.number().nullable().optional(),
  active_models_30d: z.number().nullable().optional(),
});

export const tenantRowSchema = z.object({
  rank: z.number(),
  tenant: z.string(),
  organisation: z.string().nullable().optional(),
  plan: z.string().nullable().optional(),
  requests: z.number(),
  formatted_requests: z.string(),
  percentage: z.number(),
});

export const requestHealthSchema = z.object({
  total: z.number(),
  successful: z.number(),
  failed: z.number(),
  total_formatted: z.string(),
  successful_formatted: z.string(),
  failed_formatted: z.string(),
  success_rate_pct: z.number(),
  failure_rate_pct: z.number(),
});

export const usageConcentrationSchema = z.object({
  top_tenants: z.array(tenantRowSchema),
  others: z.object({
    count: z.number(),
    requests: z.number(),
    percentage: z.number(),
  }),
  top_concentration_pct: z.number(),
  grand_total: z.number(),
});

export const throughputDataSchema = z.object({
  avg_rps: z.number(),
  peak_rps: z.number().nullable().optional(),
  peak_at: z.string().nullable().optional(),
});

const meteringDataStateSchema = z.enum(["ok", "error", "empty", "no_history"]);

const meteringResponseMetaSchema = {
  degraded: z.boolean().optional(),
  generated_at: z.string(),
  refresh_interval_seconds: z.number().optional(),
  data_state: meteringDataStateSchema.optional(),
  is_stale: z.boolean().optional(),
};

export const overviewResponseSchema = z.object({
  scope: meteringScopeSchema,
  kpis: z.array(meteringCellSchema),
  active_tenants: z.array(meteringCellSchema).default([]),
  platform_adoption: platformAdoptionSchema.nullable().optional(),
  usage_concentration: usageConcentrationSchema.nullable().optional(),
  request_health: requestHealthSchema.nullable().optional(),
  request_volume: meteringGraphSchema.nullable().optional(),
  throughput: throughputDataSchema.optional(),
  first_usage_at: z.string().nullable().optional(),
  ...meteringResponseMetaSchema,
});

export const meteringTokenKeySchema = z.enum(["input", "cached_input", "output"]);

export const meteringTokenShareSchema = z.object({
  key: meteringTokenKeySchema,
  label: z.string(),
  units: z.number(),
  percentage: z.number(),
});

export const modelConsumptionRowSchema = z.object({
  service_id: z.string(),
  name: z.string(),
  model_name: z.string().nullable().optional(),
  task_type: z.string().nullable().optional(),
  requests: z.number(),
  native_units: z.number(),
  native_unit_suffix: z.string(),
  native_breakdown: z.array(meteringTokenShareSchema).nullable().optional(),
  success_pct: z.number(),
  failure_rate_pct: z.number(),
});

export const topModelRowSchema = z.object({
  rank: z.number(),
  model_name: z.string(),
  task_type: z.string().nullable().optional(),
  consumption_pct: z.number(),
  requests: z.number(),
  formatted_requests: z.string(),
});

export const modelConsumptionSummarySchema = z.object({
  total_models: z.number().nullable().optional(),
  active_models: z.number().nullable().optional(),
  most_used: z
    .object({
      service_id: z.string().nullable().optional(),
      name: z.string().nullable().optional(),
      requests: z.number(),
    })
    .nullable()
    .optional(),
  overall_success_rate_pct: z.number().nullable().optional(),
});

export const modelConsumptionResponseSchema = z.object({
  scope: meteringScopeSchema,
  summary: modelConsumptionSummarySchema.nullable().optional(),
  top_models: z.array(topModelRowSchema).optional().default([]),
  top_models_total_requests: z.number().optional().default(0),
  breakdown: z.array(modelConsumptionRowSchema),
  ...meteringResponseMetaSchema,
});
