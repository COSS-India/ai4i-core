import { z } from 'zod';

export const logEntrySchema = z
  .object({
    timestamp: z.string(),
    level: z.string(),
    service: z.string(),
    message: z.string(),
    organization: z.string().optional(),
  })
  .passthrough();

export const logSearchResponseSchema = z.object({
  logs: z.array(logEntrySchema),
  total: z.number(),
  page: z.number(),
  size: z.number(),
  total_pages: z.number(),
});

export const logAggregationResponseSchema = z
  .object({
    total: z.number(),
    error_count: z.number(),
    warning_count: z.number(),
    info_count: z.number().optional(),
    debug_count: z.number().optional(),
    by_level: z.record(z.string(), z.number()),
    by_service: z.record(z.string(), z.number()),
  })
  .passthrough();

export const spanSchema = z
  .object({
    traceID: z.string(),
    spanID: z.string(),
    operationName: z.string(),
    startTime: z.number(),
    duration: z.number(),
    tags: z.array(z.object({ key: z.string(), value: z.unknown() })),
    logs: z.array(
      z.object({
        timestamp: z.number(),
        fields: z.array(z.object({ key: z.string(), value: z.unknown() })),
      })
    ),
    processID: z.string(),
    references: z
      .array(
        z.object({
          refType: z.string(),
          traceID: z.string(),
          spanID: z.string(),
        })
      )
      .optional(),
  })
  .passthrough();

export const processSchema = z.object({
  serviceName: z.string(),
  tags: z.array(z.object({ key: z.string(), value: z.unknown() })),
});

export const traceSchema = z.object({
  traceID: z.string(),
  spans: z.array(spanSchema),
  processes: z.record(z.string(), processSchema),
  startTime: z.number(),
  duration: z.number(),
});

export const traceSearchResponseSchema = z.object({
  data: z.array(traceSchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
});

export const telemetryTraceRecordSchema = z.object({
  trace_id: z.string(),
  task_type: z.string().nullable().optional(),
  status: z.string(),
  url: z.string().nullable().optional(),
  tenant_id: z.string().nullable().optional(),
  timestamp: z.string().nullable().optional(),
  service: z.string().nullable().optional(),
});

const telemetryByLevelSchema = z.preprocess((raw: unknown) => {
  if (raw && typeof raw === 'object') {
    const o = raw as Record<string, number>;
    return {
      success: Number(o.success ?? o.Success ?? 0),
      failure: Number(o.failure ?? o.Failure ?? o.fail ?? o.Fail ?? 0),
    };
  }
  return { success: 0, failure: 0 };
}, z.object({ success: z.number(), failure: z.number() }));

export const telemetryTraceSearchResponseSchema = z.preprocess((raw: unknown) => {
  if (!raw || typeof raw !== 'object') return raw;
  const r = raw as Record<string, unknown>;
  return {
    ...r,
    pageSize: r.pageSize ?? r.page_size ?? 15,
    data: r.data ?? [],
  };
}, z.object({
  data: z.array(telemetryTraceRecordSchema),
  total: z.number(),
  page: z.number(),
  pageSize: z.number(),
  aggregations: z.object({
    total: z.number(),
    by_level: telemetryByLevelSchema,
    by_task: z.record(z.string(), z.number()).optional(),
  }),
}));

export const telemetrySpanSchema = z
  .object({
    name: z.string(),
    context: z
      .object({
        trace_id: z.string().optional(),
        span_id: z.string().optional(),
        trace_state: z.string().optional(),
      })
      .passthrough(),
    kind: z.string().nullish(),
    attributes: z.record(z.string(), z.unknown()).optional().default({}),
    timestamp: z.string().nullable().optional(),
    logger: z.string().optional(),
    taskName: z.string().optional(),
  })
  .passthrough();

export const telemetryTraceDetailSchema = z.object({
  trace_id: z.string(),
  service: z.string().optional().default(''),
  tenant_id: z.string().nullable().optional(),
  service_version: z.string().nullable().optional(),
  environment: z.string().nullable().optional(),
  hostname: z.string().nullable().optional(),
  spans: z.array(telemetrySpanSchema),
});

/** Telemetry may return `string[]` or `{ services: string[] }`. */
export const telemetryServicesNamesSchema = z.preprocess((raw: unknown) => {
  if (Array.isArray(raw)) return raw;
  if (raw && typeof raw === 'object' && 'services' in raw && Array.isArray((raw as { services: unknown }).services)) {
    return (raw as { services: string[] }).services;
  }
  return [];
}, z.array(z.string()));
