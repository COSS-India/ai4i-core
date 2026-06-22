import { z } from "zod";

const meteringWindowSchema = z.enum(["1h", "24h", "7d", "30d"]);

export const meteringCellSchema = z.object({
  key: z.string(),
  label: z.string(),
  value: z.union([z.string(), z.number(), z.null()]),
  previous: z.union([z.string(), z.number(), z.null()]).optional(),
  pct_change: z.number().nullable().optional(),
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
  step: z.string(),
  series: z.array(meteringGraphSeriesSchema),
});

export const meteringScopeSchema = z.object({
  role: z.string(),
  tenant_id: z.string().nullable(),
  organisation: z.string().nullable(),
  window: meteringWindowSchema,
});

export const platformAdoptionSchema = z.object({
  total_tenants: z.number().nullable().optional(),
  new_tenants_7d: z.number().nullable().optional(),
  active_24h: z.number().nullable().optional(),
  active_7d: z.number().nullable().optional(),
  active_30d: z.number().nullable().optional(),
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

export const overviewResponseSchema = z.object({
  scope: meteringScopeSchema,
  kpis: z.array(meteringCellSchema),
  active_tenants: z.array(meteringCellSchema).default([]),
  platform_adoption: platformAdoptionSchema.nullable().optional(),
  usage_concentration: usageConcentrationSchema.nullable().optional(),
  request_health: requestHealthSchema.nullable().optional(),
  request_volume: meteringGraphSchema.nullable().optional(),
  throughput: throughputDataSchema,
  degraded: z.boolean().optional(),
  generated_at: z.string(),
});

export const serviceEntrySchema = z.object({
  display_name: z.string(),
  requests: z.number(),
  formatted_requests: z.string(),
});

export const tenantServiceRowSchema = z.object({
  rank: z.number(),
  tenant: z.string(),
  organisation: z.string().nullable().optional(),
  services: z.record(z.string(), serviceEntrySchema),
  total: z.number(),
  formatted_total: z.string(),
});

export const tenantConsumptionResponseSchema = z.object({
  scope: meteringScopeSchema,
  tenant_ranking: z.array(tenantRowSchema),
  usage_by_service: z.array(tenantServiceRowSchema),
  throughput: throughputDataSchema.optional(),
  request_volume: meteringGraphSchema.nullable().optional(),
  degraded: z.boolean().optional(),
  generated_at: z.string(),
});

export const serviceConsumptionSummarySchema = z.object({
  active_services: z.number(),
  // Null in the empty-state: when no service has traffic in the window there is
  // no "most used" / "highest failure" service. The backend returns null for
  // these (summary itself is still present), so they must be nullable here.
  most_used: z
    .object({
      service: z.string(),
      requests: z.number(),
    })
    .nullable(),
  highest_failure_rate: z
    .object({
      service: z.string(),
      failure_rate_pct: z.number(),
    })
    .nullable(),
});

export const serviceRowSchema = z.object({
  service: z.string(),
  metering_unit: z.string(),
  requests: z.number(),
  percentage: z.number().optional(),
  native_units: z.number().nullable().optional(),
  native_unit_suffix: z.string(),
  success_pct: z.number(),
  failure_rate_pct: z.number().optional(),
  failed: z.number(),
  vs_prev_period_pct: z.number().nullable().optional(),
});

export const serviceConsumptionResponseSchema = z.object({
  scope: meteringScopeSchema,
  summary: serviceConsumptionSummarySchema.nullable().optional(),
  service_breakdown: z.array(serviceRowSchema),
  throughput: throughputDataSchema,
  request_volume: meteringGraphSchema.nullable().optional(),
  degraded: z.boolean().optional(),
  generated_at: z.string(),
});
