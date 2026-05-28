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
