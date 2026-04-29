// Observability service API client for logs and traces

import { apiClient, getJwtToken, apiEndpoints } from './api';
import { apiEndpointBuilders } from './apiEndpoints';
import { responseIndicatesTenantSuspendedOrInactive } from '../utils/tenantInactiveApiErrors';

// Use the shared Axios instance everywhere (no extra axios.create instances).
// Telemetry URL routing (if needed) is handled inside the shared `apiClient` interceptor.
const observabilityClient = apiClient;

const handleObservabilityAuthError = async (error: any): Promise<void> => {
  const status = error?.response?.status;
  const data = error?.response?.data;

  const tenantLifecycle =
    typeof status === 'number' && responseIndicatesTenantSuspendedOrInactive(status, data);

  if (typeof window === 'undefined') return;

  // Observability endpoints used to explicitly end the session on 401/403 and tenant suspension.
  if (tenantLifecycle || status === 401 || status === 403) {
    try {
      const { forceFrontendSessionEnd } = await import('../hooks/useAuth');
      forceFrontendSessionEnd();
    } catch {
      const { default: authService } = await import('./authService');
      authService.clearAuthTokens();
      authService.clearStoredUser();
      window.location.assign('/auth');
    }
  }
};

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
    // Debug: Check token before making request
    const token = getJwtToken();
    if (!token) {
      throw new Error('Authentication required. Please log in.');
    }

    const queryParams = new URLSearchParams();
    if (params.service) queryParams.append('service', params.service);
    if (params.level) queryParams.append('level', params.level);
    if (params.search_text) queryParams.append('search_text', params.search_text);
    if (params.start_time) queryParams.append('start_time', params.start_time);
    if (params.end_time) queryParams.append('end_time', params.end_time);
    if (params.tenant_id) queryParams.append('tenant_id', params.tenant_id);
    queryParams.append('page', String(params.page || 1));
    queryParams.append('size', String(params.size || 50));

    const response = await observabilityClient.get<LogSearchResponse>(
      `${apiEndpoints.telemetry.logsSearch}?${queryParams.toString()}`
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
    await handleObservabilityAuthError(error);
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
    if (error?.response?.data?.detail) {
      const detail = error.response.data.detail;
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

    const url = `${apiEndpoints.telemetry.logsAggregate}${
      queryParams.toString() ? `?${queryParams.toString()}` : ''
    }`;
    const response = await observabilityClient.get<LogAggregationResponse>(url);

    return response.data;
  } catch (error: any) {
    await handleObservabilityAuthError(error);
    console.error('Failed to get log aggregations:', error);
    // Extract error message from detail object
    let errorMessage = 'Failed to get log aggregations';
    if (error?.response?.data?.detail) {
      const detail = error.response.data.detail;
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
    const response = await observabilityClient.get<{services: string[]} | string[]>(
      apiEndpoints.telemetry.logsServices
    );

    console.log('getServicesWithLogs: Response received:', {
      dataType: typeof response.data,
      isArray: Array.isArray(response.data),
      hasServices: response.data && typeof response.data === 'object' && 'services' in response.data,
      rawData: response.data,
    });

    // Handle both response formats: {"services": [...]} or [...]
    const data = response.data;
    if (Array.isArray(data)) {
      console.log('getServicesWithLogs: Returning array directly, count:', data.length);
      return data;
    } else if (data && typeof data === 'object' && 'services' in data && Array.isArray(data.services)) {
      console.log('getServicesWithLogs: Extracting services from object, count:', data.services.length);
      return data.services;
    } else {
      console.warn('getServicesWithLogs: Unexpected services response format:', data);
      return [];
    }
  } catch (error: any) {
    await handleObservabilityAuthError(error);
    console.error('Failed to get services with logs:', {
      message: error?.message,
      status: error?.response?.status,
      statusText: error?.response?.statusText,
      data: error?.response?.data,
    });
    // Extract error message from detail object
    let errorMessage = 'Failed to get services with logs';
    if (error?.response?.data?.detail) {
      const detail = error.response.data.detail;
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

    const response = await observabilityClient.get<TraceSearchResponse>(
      `${apiEndpoints.telemetry.tracesSearch}?${queryParams.toString()}`
    );

    return response.data;
  } catch (error: any) {
    await handleObservabilityAuthError(error);
    console.error('Failed to search traces:', error);
    // Extract error message from detail object
    let errorMessage = 'Failed to search traces';
    if (error?.response?.data?.detail) {
      const detail = error.response.data.detail;
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
    const response = await observabilityClient.get<Trace>(
      apiEndpointBuilders.telemetry.traceById(traceId)
    );

    return response.data;
  } catch (error: any) {
    await handleObservabilityAuthError(error);
    console.error('Failed to get trace:', error);
    // Extract error message from detail object
    let errorMessage = 'Failed to get trace';
    if (error?.response?.data?.detail) {
      const detail = error.response.data.detail;
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
    const response = await observabilityClient.get<{services: string[]} | string[]>(
      apiEndpoints.telemetry.tracesServices
    );

    // Handle both response formats: {"services": [...]} or [...]
    const data = response.data;
    if (Array.isArray(data)) {
      return data;
    } else if (data && typeof data === 'object' && 'services' in data && Array.isArray(data.services)) {
      return data.services;
    } else {
      console.warn('Unexpected services response format:', data);
      return [];
    }
  } catch (error: any) {
    await handleObservabilityAuthError(error);
    console.error('Failed to get services with traces:', error);
    // Extract error message from detail object
    let errorMessage = 'Failed to get services with traces';
    if (error?.response?.data?.detail) {
      const detail = error.response.data.detail;
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
    const response = await observabilityClient.get<string[]>(
      apiEndpointBuilders.telemetry.operationsForService(serviceName)
    );

    return response.data;
  } catch (error: any) {
    await handleObservabilityAuthError(error);
    console.error('Failed to get operations:', error);
    // Extract error message from detail object
    let errorMessage = 'Failed to get operations';
    if (error?.response?.data?.detail) {
      const detail = error.response.data.detail;
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

