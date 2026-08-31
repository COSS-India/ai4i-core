import { z } from "zod";

const meteringWindowSchema = z.enum(["1h", "24h", "7d", "30d"]);

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
  series: z.array(meteringGraphSeriesSchema),
});

export const meteringScopeSchema = z.object({
  role: z.string(),
  tenant_id: z.string().nullable(),
  organisation: z.string().nullable(),
  window: meteringWindowSchema,
  task_types: z.array(z.string()).nullable().optional(),
});

export const platformAdoptionSchema = z.object({
  total_tenants: z.number().nullable().optional(),
  new_tenants_15d: z.number().nullable().optional(),
  active_24h: z.number().nullable().optional(),
  active_7d: z.number().nullable().optional(),
  active_30d: z.number().nullable().optional(),
  model_usage_growth_pct: z.number().nullable().optional(),
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
  ...meteringResponseMetaSchema,
});

export const serviceEntrySchema = z.object({
  display_name: z.string(),
  requests: z.number(),
  formatted_requests: z.string(),
  percentage: z.number().optional().default(0),
});

export const tenantServiceRowSchema = z.object({
  rank: z.number(),
  tenant: z.string(),
  organisation: z.string().nullable().optional(),
  services: z.record(z.string(), serviceEntrySchema),
  total: z.number(),
  formatted_total: z.string(),
  percentage: z.number().optional().default(0),
});

export const tenantConsumptionResponseSchema = z.object({
  scope: meteringScopeSchema,
  avg_requests_per_tenant: meteringCellSchema.nullable().optional(),
  tenant_ranking: z.array(tenantRowSchema),
  usage_by_service: z.array(tenantServiceRowSchema),
  throughput: throughputDataSchema.optional(),
  request_volume: meteringGraphSchema.nullable().optional(),
  ...meteringResponseMetaSchema,
});

export const modelConsumptionRowSchema = z.object({
  service_id: z.string(),
  name: z.string(),
  model_name: z.string().nullable().optional(),
  requests: z.number(),
  native_units: z.number(),
  native_unit_suffix: z.string(),
  success_pct: z.number(),
  failure_rate_pct: z.number(),
});

export const topModelRowSchema = z.object({
  rank: z.number(),
  model_name: z.string(),
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
