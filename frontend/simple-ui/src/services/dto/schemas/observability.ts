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

/** Row fields vary with the `columns` query param; only trace_id is guaranteed. */
export const telemetryTraceRecordSchema = z
  .object({
    trace_id: z.string(),
    task_type: z.string().nullable().optional(),
    status: z.string().nullable().optional(),
    url: z.string().nullable().optional(),
    tenant_id: z.string().nullable().optional(),
    timestamp: z.string().nullable().optional(),
    service: z.string().nullable().optional(),
    status_code: z.number().nullable().optional(),
    error: z.string().nullable().optional(),
    model: z.string().nullable().optional(),
    latency: z.number().nullable().optional(),
    application: z.string().nullable().optional(),
    api_key: z.string().nullable().optional(),
    end_user: z.string().nullable().optional(),
    metadata: z.union([z.array(z.string()), z.string()]).nullable().optional(),
    method: z.string().nullable().optional(),
  })
  .passthrough();

export const telemetryTraceColumnDefSchema = z
  .object({
    key: z.string(),
    label: z.string(),
    default: z.boolean(),
    filterable: z.boolean(),
    sortable: z.boolean(),
    keyword_searchable: z.boolean(),
  })
  .passthrough();

/** BE returns a bare array; older contract used `{ columns: [...] }`. */
export const telemetryTraceColumnsResponseSchema = z.preprocess((raw: unknown) => {
  if (Array.isArray(raw)) return { columns: raw };
  if (raw && typeof raw === "object" && Array.isArray((raw as { columns?: unknown }).columns)) {
    return raw;
  }
  return { columns: [] };
}, z.object({
  columns: z.array(telemetryTraceColumnDefSchema),
}));

const telemetryByLevelSchema = z.preprocess((raw: unknown) => {
  if (raw && typeof raw === 'object') {
    const o = raw as Record<string, number>;
    const success = Number(o.success ?? o.Success ?? 0);
    // OpenSearch may emit failure and/or failed; BE summary sums both.
    const failure =
      Number(o.failure ?? o.Failure ?? 0) +
      Number(o.failed ?? o.Failed ?? o.fail ?? o.Fail ?? 0);
    return { success, failure };
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
    partial: z.boolean().optional(),
  }),
  summary: z
    .object({
      success: z.number(),
      failure: z.number(),
    })
    .optional(),
}).passthrough());

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
