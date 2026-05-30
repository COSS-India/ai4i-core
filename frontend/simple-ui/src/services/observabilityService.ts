// Observability service API client for logs and traces

import { apiService } from './api';
import { apiEndpoints } from './apiEndpoints';
import {
  logAggregationResponseSchema,
  logSearchResponseSchema,
  telemetryServicesNamesSchema,
  traceSchema,
  traceSearchResponseSchema,
  telemetryTraceSearchResponseSchema,
  telemetryTraceDetailSchema,
} from './dto/schemas/observability';
import type {
  LogAggregationResponse,
  LogEntry,
  LogSearchResponse,
  Process,
  Span,
  TelemetryTraceDetail,
  TelemetryTraceRecord,
  TelemetryTraceSearchResponse,
  Trace,
  TraceSearchResponse,
} from '../types/observability';

export type {
  LogAggregationResponse,
  LogEntry,
  LogSearchResponse,
  Process,
  Span,
  TelemetrySpan,
  TelemetrySpanContext,
  TelemetryTraceDetail,
  TelemetryTraceRecord,
  TelemetryTraceSearchAggregations,
  TelemetryTraceSearchResponse,
  Trace,
  TraceSearchResponse,
} from '../types/observability';

// Empty base URL uses same-origin paths so Next.js dev rewrites can proxy to the backend.
const TELEMETRY_SERVICE_URL = process.env.NEXT_PUBLIC_TELEMETRY_SERVICE_URL ?? '';

const telemetryUrl = (path: string): string => `${TELEMETRY_SERVICE_URL}${path}`;

/** Remove when GET /telemetry/traces/search is live on dev. */
const USE_MOCK_TELEMETRY_TRACES =
  process.env.NEXT_PUBLIC_MOCK_TELEMETRY_TRACES !== 'false';

const MOCK_TELEMETRY_TRACE_RECORDS: TelemetryTraceRecord[] = [
  {
    trace_id: '0xf1e2d3c4b5a6978869584736a5b4c3d2',
    task_type: 'NMT',
    status: 'Fail',
    url: '/api/v1/nmt/inference',
    tenant_id: '2',
    timestamp: '2026-05-28T18:16:00.416613+00:00',
  },
  {
    trace_id: '0xe8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3',
    task_type: 'OCR',
    status: 'Success',
    url: '/api/v1/ocr/inference',
    tenant_id: '2',
    timestamp: '2026-05-28T18:17:00.416613+00:00',
  },
];

const MOCK_TELEMETRY_AGGREGATIONS = {
  total: 4567,
  by_level: { success: 3766, failure: 234 },
};

const MOCK_TELEMETRY_TRACE_DETAIL: TelemetryTraceDetail = {
  trace_id: '0xc78a7cde764dd2b4022ff59a0b3d91a7',
  service: 'ai4x-inference',
  tenant_id: 'system',
  service_version: '1.0.0',
  environment: 'development',
  hostname: 'TI-MAC-085-VINU.local',
  spans: [
    {
      name: 'request',
      context: {
        trace_id: '0xc78a7cde764dd2b4022ff59a0b3d91a7',
        span_id: '0x7a11003141837e89',
        trace_state: '',
      },
      kind: 'SpanKind.INTERNAL',
      attributes: {
        total_time_ms: 23224.33,
        url: '/api/v1/nmt/inference',
        method: 'POST',
        status: 'success',
        status_code: 200,
      },
      timestamp: '2026-05-28T18:14:35.416613+00:00',
      logger: 'trace.request_span',
      taskName: 'Task-5',
    },
    {
      name: 'model',
      context: {
        trace_id: '0xc78a7cde764dd2b4022ff59a0b3d91a7',
        span_id: '0xb25c5da63541b5ba',
        trace_state: '',
      },
      kind: 'SpanKind.INTERNAL',
      attributes: {
        total_time_ms: 1345.37,
        model_name: 'indictrans-gpu-t4',
        model_version: 'unknown',
        task_type: 'NMT',
      },
      timestamp: '2026-05-28T18:14:13.538874+00:00',
      logger: 'trace.request_span',
      taskName: 'Task-5',
    },
    {
      name: 'ai-inference',
      context: {
        trace_id: '0xc78a7cde764dd2b4022ff59a0b3d91a7',
        span_id: '0x911666d83430d521',
        trace_state: '',
      },
      kind: 'SpanKind.INTERNAL',
      attributes: {
        total_time_ms: 8525.23,
        input_tokens: 1,
        output_tokens: 4,
        input_type: 'text',
        output_type: 'text',
        status: 'success',
        status_code: 200,
      },
      timestamp: '2026-05-28T18:14:28.811737+00:00',
      logger: 'trace.request_span',
      taskName: 'Task-5',
    },
  ],
};

/** Path segment for GET /telemetry/traces/{id} (strip optional 0x prefix). */
export function telemetryTraceIdForApi(traceId: string): string {
  return traceId.trim().replace(/^0x/i, '');
}

function buildMockTelemetryTracesResponse(params: {
  taskType?: string;
  level?: string;
  search?: string;
  tenant_id?: string;
  page?: number;
  pageSize?: number;
}): TelemetryTraceSearchResponse {
  let rows = [...MOCK_TELEMETRY_TRACE_RECORDS];
  if (params.taskType) {
    const taskType = params.taskType.toUpperCase();
    rows = rows.filter((row) => row.task_type.toUpperCase() === taskType);
  }
  if (params.level) {
    const level = params.level.toLowerCase();
    rows = rows.filter((row) => row.status.toLowerCase() === level);
  }
  if (params.search) {
    const q = params.search.toLowerCase();
    rows = rows.filter(
      (row) =>
        row.trace_id.toLowerCase().includes(q) ||
        row.url.toLowerCase().includes(q) ||
        row.task_type.toLowerCase().includes(q)
    );
  }
  if (params.tenant_id) {
    rows = rows.filter((row) => row.tenant_id === params.tenant_id);
  }

  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? 15;
  const start = (page - 1) * pageSize;

  return {
    data: rows.slice(start, start + pageSize),
    total: rows.length,
    page,
    pageSize,
    aggregations: MOCK_TELEMETRY_AGGREGATIONS,
  };
}

/**
 * Search logs with filters
 */
export const searchLogs = async (
  params: {
    service?: string;
    level?: string;
    search_text?: string;
    start_time?: string;
    end_time?: string;
    page?: number;
    size?: number;
    tenant_id?: string; // Admin-only: filter by tenant_id
  }
): Promise<LogSearchResponse> => {
  try {
    const queryParams = new URLSearchParams();
    if (params.service) queryParams.append('service', params.service);
    if (params.level) queryParams.append('level', params.level);
    if (params.search_text) queryParams.append('search_text', params.search_text);
    if (params.start_time) queryParams.append('start_time', params.start_time);
    if (params.end_time) queryParams.append('end_time', params.end_time);
    if (params.tenant_id) queryParams.append('tenant_id', params.tenant_id);
    queryParams.append('page', String(params.page || 1));
    queryParams.append('size', String(params.size || 50));

    const response = await apiService.get(
      telemetryUrl(`${apiEndpoints.telemetry.logsSearch}?${queryParams.toString()}`),
      { timeout: 30000, responseSchema: logSearchResponseSchema }
    );

    console.log('searchLogs: Response received:', {
      total: response.data?.total,
      logsCount: response.data?.logs?.length || 0,
      logsType: typeof response.data?.logs,
      isArray: Array.isArray(response.data?.logs),
      fullResponse: response.data,
    });

    // Ensure logs is always an array
    if (response.data && !Array.isArray(response.data.logs)) {
      console.error('API returned non-array logs!', response.data);
      response.data.logs = [];
    }

    return response.data;
  } catch (error: any) {
    console.error('Failed to search logs:', {
      message: error?.message,
      status: error?.response?.status,
      statusText: error?.response?.statusText,
      data: error?.response?.data,
      url: error?.config?.url,
      headers: error?.config?.headers,
    });
    // Extract error message from detail object
    let errorMessage = 'Failed to search logs';
    const detail = error?.response?.data?.detail;
    if (detail) {
      if (typeof detail === 'string') {
        errorMessage = detail;
      } else if (typeof detail === 'object' && detail.message) {
        errorMessage = detail.message;
      } else if (typeof detail === 'object') {
        errorMessage = JSON.stringify(detail);
      }
    } else if (error?.message) {
      errorMessage = error.message;
    }
    throw new Error(errorMessage);
  }
};

/**
 * Get log aggregations
 */
export const getLogAggregations = async (
  params?: {
    start_time?: string;
    end_time?: string;
  }
): Promise<LogAggregationResponse> => {
  try {
    const queryParams = new URLSearchParams();
    if (params?.start_time) queryParams.append('start_time', params.start_time);
    if (params?.end_time) queryParams.append('end_time', params.end_time);

    const url = `${apiEndpoints.telemetry.logsAggregate}${queryParams.toString() ? `?${queryParams.toString()}` : ''}`;
    const response = await apiService.get(telemetryUrl(url), {
      timeout: 30000,
      responseSchema: logAggregationResponseSchema,
    });

    return response.data;
  } catch (error: any) {
    console.error('Failed to get log aggregations:', error);
    // Extract error message from detail object
    let errorMessage = 'Failed to get log aggregations';
    const detail = error?.response?.data?.detail;
    if (detail) {
      if (typeof detail === 'string') {
        errorMessage = detail;
      } else if (typeof detail === 'object' && detail.message) {
        errorMessage = detail.message;
      } else if (typeof detail === 'object') {
        errorMessage = JSON.stringify(detail);
      }
    } else if (error?.message) {
      errorMessage = error.message;
    }
    throw new Error(errorMessage);
  }
};

/**
 * Get list of services with logs
 */
export const getServicesWithLogs = async (): Promise<string[]> => {
  try {
    const response = await apiService.get(telemetryUrl(apiEndpoints.telemetry.logsServices), {
      timeout: 30000,
      responseSchema: telemetryServicesNamesSchema,
    });

    console.log('getServicesWithLogs: Response received:', {
      count: response.data?.length ?? 0,
    });

    return response.data;
  } catch (error: any) {
    console.error('Failed to get services with logs:', {
      message: error?.message,
      status: error?.response?.status,
      statusText: error?.response?.statusText,
      data: error?.response?.data,
    });
    // Extract error message from detail object
    let errorMessage = 'Failed to get services with logs';
    const detail = error?.response?.data?.detail;
    if (detail) {
      if (typeof detail === 'string') {
        errorMessage = detail;
      } else if (typeof detail === 'object' && detail.message) {
        errorMessage = detail.message;
      } else if (typeof detail === 'object') {
        errorMessage = JSON.stringify(detail);
      }
    } else if (error?.message) {
      errorMessage = error.message;
    }
    throw new Error(errorMessage);
  }
};

/**
 * Resolve `tenant_id` query param from role:
 * - TENANT ADMIN: always scope to their tenant (from auth).
 * - ADMIN: optional filter when a tenant is selected in the UI.
 * - Other allowed roles: scope to their tenant when present.
 */
export function resolveTelemetryTenantId(params: {
  isAdmin: boolean;
  isTenantAdmin: boolean;
  selectedTenantId?: string;
  authTenantId?: string | null;
}): string | undefined {
  const authTenant = params.authTenantId?.trim();

  if (params.isTenantAdmin) {
    return authTenant || undefined;
  }

  if (params.isAdmin) {
    const selected = params.selectedTenantId?.trim();
    return selected || undefined;
  }

  return authTenant || undefined;
}

/**
 * Search telemetry traces (unified list + aggregations).
 * GET /api/v1/telemetry/traces/search
 */
export const searchTelemetryTraces = async (
  params: {
    taskType?: string;
    level?: string;
    search?: string;
    startDate?: string;
    endDate?: string;
    page?: number;
    pageSize?: number;
    tenant_id?: string;
  }
): Promise<TelemetryTraceSearchResponse> => {
  if (USE_MOCK_TELEMETRY_TRACES) {
    return Promise.resolve(buildMockTelemetryTracesResponse(params));
  }

  try {
    const queryParams = new URLSearchParams();
    if (params.taskType) queryParams.append('TaskType', params.taskType.toUpperCase());
    if (params.level) queryParams.append('Level', params.level);
    if (params.search) queryParams.append('search', params.search);
    if (params.startDate) queryParams.append('startDate', params.startDate);
    if (params.endDate) queryParams.append('endDate', params.endDate);
    if (params.tenant_id) queryParams.append('tenant_id', params.tenant_id);
    queryParams.append('page', String(params.page ?? 1));
    queryParams.append('pageSize', String(params.pageSize ?? 15));

    const response = await apiService.get(
      telemetryUrl(`${apiEndpoints.telemetry.tracesSearch}?${queryParams.toString()}`),
      { timeout: 30000, responseSchema: telemetryTraceSearchResponseSchema }
    );

    return response.data;
  } catch (error: any) {
    console.error('Failed to search telemetry traces:', error);
    let errorMessage = 'Failed to search traces';
    const detail = error?.response?.data?.detail;
    if (detail) {
      if (typeof detail === 'string') {
        errorMessage = detail;
      } else if (typeof detail === 'object' && detail.message) {
        errorMessage = detail.message;
      } else if (typeof detail === 'object') {
        errorMessage = JSON.stringify(detail);
      }
    } else if (error?.message) {
      errorMessage = error.message;
    }
    throw new Error(errorMessage);
  }
};

/**
 * Search traces (Jaeger-style; legacy)
 */
export const searchTraces = async (
  params: {
    service?: string;
    operation?: string;
    start_time?: number;
    end_time?: number;
    limit?: number;
    tags?: Record<string, string>;
  }
): Promise<TraceSearchResponse> => {
  try {
    const queryParams = new URLSearchParams();
    if (params.service) queryParams.append('service', params.service);
    if (params.operation) queryParams.append('operation', params.operation);
    if (params.start_time) queryParams.append('start_time', String(params.start_time));
    if (params.end_time) queryParams.append('end_time', String(params.end_time));
    if (params.limit) queryParams.append('limit', String(params.limit));
    if (params.tags) {
      Object.entries(params.tags).forEach(([key, value]) => {
        queryParams.append(`tags.${key}`, value);
      });
    }

    const response = await apiService.get(
      telemetryUrl(`${apiEndpoints.telemetry.tracesSearch}?${queryParams.toString()}`),
      { timeout: 30000, responseSchema: traceSearchResponseSchema }
    );

    return response.data;
  } catch (error: any) {
    console.error('Failed to search traces:', error);
    // Extract error message from detail object
    let errorMessage = 'Failed to search traces';
    const detail = error?.response?.data?.detail;
    if (detail) {
      if (typeof detail === 'string') {
        errorMessage = detail;
      } else if (typeof detail === 'object' && detail.message) {
        errorMessage = detail.message;
      } else if (typeof detail === 'object') {
        errorMessage = JSON.stringify(detail);
      }
    } else if (error?.message) {
      errorMessage = error.message;
    }
    throw new Error(errorMessage);
  }
};

/**
 * Get telemetry trace detail by ID.
 * GET /api/v1/telemetry/traces/{traceId}
 */
export const getTelemetryTraceById = async (traceId: string): Promise<TelemetryTraceDetail> => {
  const apiTraceId = telemetryTraceIdForApi(traceId);

  if (USE_MOCK_TELEMETRY_TRACES) {
    return Promise.resolve({
      ...MOCK_TELEMETRY_TRACE_DETAIL,
      trace_id: traceId.trim() || MOCK_TELEMETRY_TRACE_DETAIL.trace_id,
    });
  }

  try {
    const response = await apiService.get(
      telemetryUrl(apiEndpoints.telemetry.traceById(apiTraceId)),
      { timeout: 30000, responseSchema: telemetryTraceDetailSchema }
    );
    return response.data;
  } catch (error: any) {
    console.error('Failed to get telemetry trace:', error);
    let errorMessage = 'Failed to get trace';
    const detail = error?.response?.data?.detail;
    if (detail) {
      if (typeof detail === 'string') {
        errorMessage = detail;
      } else if (typeof detail === 'object' && detail.message) {
        errorMessage = detail.message;
      } else if (typeof detail === 'object') {
        errorMessage = JSON.stringify(detail);
      }
    } else if (error?.message) {
      errorMessage = error.message;
    }
    throw new Error(errorMessage);
  }
};

/**
 * Get trace by ID (Jaeger-style; legacy)
 */
export const getTraceById = async (traceId: string): Promise<Trace> => {
  try {
    const response = await apiService.get(telemetryUrl(apiEndpoints.telemetry.traceById(traceId)), {
      timeout: 30000,
      responseSchema: traceSchema,
    });

    return response.data;
  } catch (error: any) {
    console.error('Failed to get trace:', error);
    // Extract error message from detail object
    let errorMessage = 'Failed to get trace';
    const detail = error?.response?.data?.detail;
    if (detail) {
      if (typeof detail === 'string') {
        errorMessage = detail;
      } else if (typeof detail === 'object' && detail.message) {
        errorMessage = detail.message;
      } else if (typeof detail === 'object') {
        errorMessage = JSON.stringify(detail);
      }
    } else if (error?.message) {
      errorMessage = error.message;
    }
    throw new Error(errorMessage);
  }
};

/**
 * Get list of services with traces
 */
export const getServicesWithTraces = async (): Promise<string[]> => {
  try {
    const response = await apiService.get(telemetryUrl(apiEndpoints.telemetry.tracesServices), {
      timeout: 30000,
      responseSchema: telemetryServicesNamesSchema,
    });

    return response.data;
  } catch (error: any) {
    console.error('Failed to get services with traces:', error);
    // Extract error message from detail object
    let errorMessage = 'Failed to get services with traces';
    const detail = error?.response?.data?.detail;
    if (detail) {
      if (typeof detail === 'string') {
        errorMessage = detail;
      } else if (typeof detail === 'object' && detail.message) {
        errorMessage = detail.message;
      } else if (typeof detail === 'object') {
        errorMessage = JSON.stringify(detail);
      }
    } else if (error?.message) {
      errorMessage = error.message;
    }
    throw new Error(errorMessage);
  }
};

/**
 * Get operations for a service
 */
export const getOperationsForService = async (serviceName: string): Promise<string[]> => {
  try {
    const response = await apiService.get(
      telemetryUrl(apiEndpoints.telemetry.traceServiceOperations(serviceName)),
      { timeout: 30000, responseSchema: telemetryServicesNamesSchema }
    );

    return response.data;
  } catch (error: any) {
    console.error('Failed to get operations:', error);
    // Extract error message from detail object
    let errorMessage = 'Failed to get operations';
    const detail = error?.response?.data?.detail;
    if (detail) {
      if (typeof detail === 'string') {
        errorMessage = detail;
      } else if (typeof detail === 'object' && detail.message) {
        errorMessage = detail.message;
      } else if (typeof detail === 'object') {
        errorMessage = JSON.stringify(detail);
      }
    } else if (error?.message) {
      errorMessage = error.message;
    }
    throw new Error(errorMessage);
  }
};
