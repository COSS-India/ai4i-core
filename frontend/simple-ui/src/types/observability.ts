/**
 * Telemetry / observability API response types.
 */

export interface LogEntry {
  timestamp: string;
  level: string;
  service: string;
  message: string;
  organization?: string;
  [key: string]: unknown;
}

export interface LogSearchResponse {
  logs: LogEntry[];
  total: number;
  page: number;
  size: number;
  total_pages: number;
}

export interface LogAggregationResponse {
  total: number;
  error_count: number;
  warning_count: number;
  info_count?: number;
  debug_count?: number;
  by_level: Record<string, number>;
  by_service: Record<string, number>;
}

export interface TraceTag {
  key: string;
  value: unknown;
}

export interface TraceLogField {
  key: string;
  value: unknown;
}

export interface TraceSpanLog {
  timestamp: number;
  fields: TraceLogField[];
}

export interface TraceSpanReference {
  refType: string;
  traceID: string;
  spanID: string;
}

export interface Span {
  traceID: string;
  spanID: string;
  operationName: string;
  startTime: number;
  duration: number;
  tags: TraceTag[];
  logs: TraceSpanLog[];
  processID: string;
  references?: TraceSpanReference[];
}

export interface Process {
  serviceName: string;
  tags: TraceTag[];
}

export interface Trace {
  traceID: string;
  spans: Span[];
  processes: Record<string, Process>;
  startTime: number;
  duration: number;
}

export interface TraceSearchResponse {
  data: Trace[];
  total: number;
  limit: number;
  offset: number;
}

/** Row from GET /telemetry/traces/search (unified search + aggregations). */
export interface TelemetryTraceRecord {
  trace_id: string;
  task_type: string;
  status: string;
  url: string;
  tenant_id: string;
  timestamp: string;
}

export interface TelemetryTraceSearchAggregations {
  total: number;
  by_level: {
    success: number;
    failure: number;
  };
}

export interface TelemetryTraceSearchResponse {
  data: TelemetryTraceRecord[];
  total: number;
  page: number;
  pageSize: number;
  aggregations: TelemetryTraceSearchAggregations;
}

export interface TelemetrySpanContext {
  trace_id: string;
  span_id: string;
  trace_state: string;
}

export interface TelemetrySpan {
  name: string;
  context: TelemetrySpanContext;
  kind: string;
  attributes: Record<string, unknown>;
  timestamp: string;
  logger?: string;
  taskName?: string;
}

export interface TelemetryTraceDetail {
  trace_id: string;
  service: string;
  tenant_id: string;
  service_version: string;
  environment: string;
  hostname: string;
  spans: TelemetrySpan[];
}
