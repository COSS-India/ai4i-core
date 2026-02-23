// Observability service API client for logs and traces

import axios, { AxiosInstance } from 'axios';
import { getJwtToken } from './api';

// Telemetry service runs on port 8084 (different from API gateway on 8080)
const TELEMETRY_SERVICE_URL = process.env.NEXT_PUBLIC_TELEMETRY_SERVICE_URL ;

// Create dedicated axios instance for observability endpoints
const observabilityClient: AxiosInstance = axios.create({
  baseURL: TELEMETRY_SERVICE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add request interceptor to inject JWT token
observabilityClient.interceptors.request.use(
  (config: any) => {
    const jwtToken = getJwtToken();
    if (jwtToken) {
      config.headers['Authorization'] = `Bearer ${jwtToken}`;
      config.headers['x-auth-source'] = 'BOTH';
      config.headers['X-Auth-Source'] = 'BOTH';
      console.log('✅ Observability request with token:', {
        url: config.url,
        hasAuth: !!config.headers['Authorization'],
        tokenLength: jwtToken.length,
      });
    } else {
      console.error('❌ Observability request made WITHOUT JWT token:', config.url);
      console.error('Token check:', {
        localStorage: typeof window !== 'undefined' ? localStorage.getItem('access_token') : 'N/A',
        sessionStorage: typeof window !== 'undefined' ? sessionStorage.getItem('access_token') : 'N/A',
      });
    }
    return config;
  },
  (error: any) => {
    return Promise.reject(error);
  }
);

// Add response interceptor for error logging
observabilityClient.interceptors.response.use(
  (response: any) => response,
  (error: any) => {
    console.error('Observability API error:', {
      url: error.config?.url,
      status: error.response?.status,
      statusText: error.response?.statusText,
      data: error.response?.data,
      message: error.message,
    });
    return Promise.reject(error);
  }
);

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
      console.error('⚠️ searchLogs called without JWT token!');
      throw new Error('Authentication required. Please log in.');
    }
    console.log('searchLogs: Making request with token (length:', token.length, ')');
    
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
      `/api/v1/telemetry/logs/search?${queryParams.toString()}`
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

    const url = `/api/v1/telemetry/logs/aggregate${queryParams.toString() ? `?${queryParams.toString()}` : ''}`;
    const response = await observabilityClient.get<LogAggregationResponse>(url);

    return response.data;
  } catch (error: any) {
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
      '/api/v1/telemetry/logs/services'
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
      `/api/v1/telemetry/traces/search?${queryParams.toString()}`
    );

    return response.data;
  } catch (error: any) {
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
      `/api/v1/telemetry/traces/${traceId}`
    );

    return response.data;
  } catch (error: any) {
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
      '/api/v1/telemetry/traces/services'
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
      `/api/v1/telemetry/traces/services/${serviceName}/operations`
    );

    return response.data;
  } catch (error: any) {
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

