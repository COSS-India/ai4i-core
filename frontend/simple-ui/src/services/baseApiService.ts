import axios from 'axios';
import { apiClient } from './api';

type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

/**
 * Shared request options for wrapper calls.
 * Keep this aligned with Axios request options that services are allowed to customize.
 */
export type BaseApiRequestOptions = {
  method?: HttpMethod;
  data?: unknown;
  headers?: Record<string, string>;
  params?: Record<string, unknown>;
  timeout?: number;
};

type ApiEnvelope<T> = {
  success?: boolean;
  data?: T;
};

export type BaseApiError = Error & {
  status?: number;
  responseData?: unknown;
  originalError?: unknown;
};

/**
 * Wrapper response format for callers that need metadata (for example, request duration headers).
 */
export type BaseApiResponse<T> = {
  data: T;
  headers: Record<string, string>;
  status: number;
};

/**
 * Normalize backend response envelopes.
 * Supports both raw payloads and `{ success, data }` envelope responses.
 */
const unwrapApiResponse = <T>(payload: unknown): T => {
  if (
    payload &&
    typeof payload === 'object' &&
    'success' in payload &&
    'data' in payload
  ) {
    return (payload as ApiEnvelope<T>).data as T;
  }
  return payload as T;
};

/**
 * Map Axios errors to a stable, app-level error shape consumed across services.
 */
const mapApiError = (error: unknown): never => {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status;
    const responseData = error.response?.data;
    let message = `HTTP error! status: ${status ?? 'unknown'}`;

    if (responseData && typeof responseData === 'object') {
      const asObject = responseData as Record<string, unknown>;
      const detail = asObject.detail;
      const responseMessage = asObject.message;
      if (typeof detail === 'string') {
        message = detail;
      } else if (detail && typeof detail === 'object') {
        const detailMessage = (detail as Record<string, unknown>).message;
        message =
          typeof detailMessage === 'string'
            ? detailMessage
            : JSON.stringify(detail);
      } else if (typeof responseMessage === 'string') {
        message = responseMessage;
      } else if (error.message) {
        message = error.message;
      }
    } else if (typeof responseData === 'string') {
      message = responseData;
    } else if (error.message) {
      message = error.message;
    }

    const mappedError = new Error(message) as BaseApiError;
    mappedError.status = status;
    mappedError.responseData = responseData;
    mappedError.originalError = error;
    throw mappedError;
  }

  if (error instanceof Error) {
    throw error;
  }

  throw new Error(String(error));
};

/**
 * Centralized API wrapper used by all services.
 *
 * Usage:
 * - Prefer `get/post/put/patch/delete` for standard calls.
 * - Use `requestWithMeta` when status/headers are needed.
 * - Errors are normalized by `mapApiError` and thrown as `BaseApiError`.
 */
export const baseApiService = {
  /**
   * Execute a request and return data + headers + status.
   */
  async requestWithMeta<T>(
    url: string,
    options: BaseApiRequestOptions = {}
  ): Promise<BaseApiResponse<T>> {
    const { method = 'GET', data, headers, params, timeout } = options;

    try {
      const response = await apiClient.request<T>({
        url,
        method,
        data,
        headers,
        params,
        timeout,
      });
      return {
        data: unwrapApiResponse<T>(response.data),
        headers: response.headers as Record<string, string>,
        status: response.status,
      };
    } catch (error) {
      return mapApiError(error);
    }
  },

  /**
   * Execute a request and return only normalized response data.
   */
  async request<T>(url: string, options: BaseApiRequestOptions = {}): Promise<T> {
    const response = await this.requestWithMeta<T>(url, options);
    return response.data;
  },

  /** Convenience wrapper for GET requests. */
  get<T>(
    url: string,
    options: Omit<BaseApiRequestOptions, 'method' | 'data'> = {}
  ): Promise<T> {
    return this.request<T>(url, { ...options, method: 'GET' });
  },

  /** Convenience wrapper for POST requests. */
  post<T>(
    url: string,
    data?: unknown,
    options: Omit<BaseApiRequestOptions, 'method' | 'data'> = {}
  ): Promise<T> {
    return this.request<T>(url, { ...options, method: 'POST', data });
  },

  /** Convenience wrapper for PUT requests. */
  put<T>(
    url: string,
    data?: unknown,
    options: Omit<BaseApiRequestOptions, 'method' | 'data'> = {}
  ): Promise<T> {
    return this.request<T>(url, { ...options, method: 'PUT', data });
  },

  /** Convenience wrapper for PATCH requests. */
  patch<T>(
    url: string,
    data?: unknown,
    options: Omit<BaseApiRequestOptions, 'method' | 'data'> = {}
  ): Promise<T> {
    return this.request<T>(url, { ...options, method: 'PATCH', data });
  },

  /** Convenience wrapper for DELETE requests. */
  delete<T>(
    url: string,
    options: Omit<BaseApiRequestOptions, 'method' | 'data'> = {}
  ): Promise<T> {
    return this.request<T>(url, { ...options, method: 'DELETE' });
  },
};

export default baseApiService;
