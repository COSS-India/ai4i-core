// Observability service API client for logs and traces

import { apiService } from './api';
import { apiEndpoints } from './apiEndpoints';
import {
  logAggregationResponseSchema,
  logSearchResponseSchema,
  telemetryServicesNamesSchema,
  traceSchema,
  traceSearchResponseSchema,
} from './dto/schemas/observability';

// Telemetry service runs on port 8084 (different from API gateway on 8080)
const TELEMETRY_SERVICE_URL = process.env.NEXT_PUBLIC_TELEMETRY_SERVICE_URL ;

const telemetryUrl = (path: string): string => `${TELEMETRY_SERVICE_URL}${path}`;

// Types
export interface LogEntry {
  timestamp: string;
  level: string;
  service: string;
  message: string;
  organization?: string;
  [key: string]: any;
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
  info_count?: number;  // Optional, calculated from by_level if needed
  debug_count?: number;  // Optional, calculated from by_level if needed
  by_level: Record<string, number>;
  by_service: Record<string, number>;
}

export interface Trace {
  traceID: string;
  spans: Span[];
  processes: Record<string, Process>;
  startTime: number;
  duration: number;
}

export interface Span {
  traceID: string;
  spanID: string;
  operationName: string;
  startTime: number;
  duration: number;
  tags: Array<{ key: string; value: any }>;
  logs: Array<{ timestamp: number; fields: Array<{ key: string; value: any }> }>;
  processID: string;
  references?: Array<{ refType: string; traceID: string; spanID: string }>;
}

export interface Process {
  serviceName: string;
  tags: Array<{ key: string; value: any }>;
}

export interface TraceSearchResponse {
  data: Trace[];
  total: number;
  limit: number;
  offset: number;
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
 * Search traces
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
 * Get trace by ID
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

