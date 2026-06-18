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

/** Path segment for GET /telemetry/traces/{id} (keep 0x prefix as returned by search). */
export function telemetryTraceIdForApi(traceId: string): string {
  return encodeURIComponent(traceId.trim());
}

/** Map UI status filter to OpenSearch `attributes.status` values. */
function mapStatusFilter(level?: string): string | undefined {
  if (!level?.trim()) return undefined;
  const v = level.trim().toLowerCase();
  if (v === 'success') return 'success';
  if (v === 'fail' || v === 'failure') return 'failure';
  return v;
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
    startDate?: string;
    endDate?: string;
    page?: number;
    pageSize?: number;
    tenant_id?: string;
  }
): Promise<TelemetryTraceSearchResponse> => {
  try {
    const queryParams = new URLSearchParams();
    if (params.taskType) queryParams.append('task_type', params.taskType.toUpperCase());
    const statusFilter = mapStatusFilter(params.level);
    if (statusFilter) queryParams.append('status_filter', statusFilter);
    if (params.startDate) queryParams.append('start_date', params.startDate);
    if (params.endDate) queryParams.append('end_date', params.endDate);
    if (params.tenant_id) queryParams.append('tenant_id', params.tenant_id);
    queryParams.append('page', String(params.page ?? 1));
    queryParams.append('page_size', String(params.pageSize ?? 15));

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
