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

/** Telemetry may return `string[]` or `{ services: string[] }`. */
export const telemetryServicesNamesSchema = z.preprocess((raw: unknown) => {
  if (Array.isArray(raw)) return raw;
  if (raw && typeof raw === 'object' && 'services' in raw && Array.isArray((raw as { services: unknown }).services)) {
    return (raw as { services: string[] }).services;
  }
  return [];
}, z.array(z.string()));
