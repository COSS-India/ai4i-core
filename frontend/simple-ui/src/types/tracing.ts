// TypeScript types for Jaeger trace data

export interface JaegerTag {
  key: string;
  value: string;
  type?: string;
}

export interface JaegerLog {
  timestamp: number;
  fields: JaegerTag[];
}

export interface JaegerReference {
  refType: 'CHILD_OF' | 'FOLLOWS_FROM';
  traceID: string;
  spanID: string;
}

export interface JaegerSpan {
  traceID: string;
  spanID: string;
  parentSpanID?: string;
  operationName: string;
  startTime: number;
  duration: number;
  tags: JaegerTag[];
  logs: JaegerLog[];
  references?: JaegerReference[];
  processID: string;
  flags?: number;
  warnings?: string[];
}

export interface JaegerProcess {
  serviceName: string;
  tags: JaegerTag[];
}

export interface JaegerTrace {
  traceID: string;
  spans: JaegerSpan[];
  processes: Record<string, JaegerProcess>;
  warnings?: string[];
}

export interface JaegerService {
  name: string;
  operations?: Array<{
    name: string;
    spanKind: string;
  }>;
}

export interface TraceSearchParams {
  service?: string;
  operation?: string;
  tags?: Record<string, string>;
  startTime?: number;
  endTime?: number;
  limit?: number;
  minDuration?: string;
  maxDuration?: string;
  lookback?: string;
}

// Transformed trace step for visualization
export interface TraceStep {
  id: number;
  title: string;
  description: string;
  userAction: string;
  icon: string;
  serviceName: string;
  operationName: string;
  duration: number;
  startTime: number;
  status: 'pending' | 'active' | 'complete' | 'error';
  hasContextLayers: boolean;
  contextLayers?: ContextLayer[];
  span: JaegerSpan;
}

export interface ContextLayer {
  type: 'auth' | 'contract' | 'inference' | 'metadata';
  badge: string;
  title: string;
  items: string[];
  note?: string;
}

export interface TraceStatistics {
  totalSpans: number;
  totalDuration: number;
  serviceCount: number;
  errorCount: number;
  slowestSpan?: JaegerSpan;
  fastestSpan?: JaegerSpan;
}

