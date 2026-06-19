import {
  AxiosError,
  AxiosInstance,
  AxiosRequestConfig,
  AxiosResponse,
  isCancel,
  Method,
} from 'axios';
import type { ZodTypeAny } from 'zod';
import { parseResponseData } from './dto/parseResponseData';
import { handleApiError, type ErrorHandlerService } from '../utils/errorHandler';

const warnOnMissingResponseSchema =
  process.env.NODE_ENV === 'development' &&
  process.env.NEXT_PUBLIC_API_STRICT_RESPONSE_VALIDATION === 'true';

type ApiRequestHeaders = Record<string, string>;
const DEFAULT_API_HEADERS: ApiRequestHeaders = {
  'Content-Type': 'application/json',
  Accept: 'application/json',
};

/**
 * Request config accepted by the base API wrapper.
 * Keeps axios options available while standardizing header shape.
 */
export interface BaseApiRequestConfig<D = any> extends AxiosRequestConfig<D> {
  headers?: ApiRequestHeaders;
  /** When set, `response.data` is validated (and replaced with the parsed value). */
  responseSchema?: ZodTypeAny;
  /** Skip the global browser alert for this request (e.g. silent auth bootstrap). */
  suppressErrorAlert?: boolean;
  /** Service context for service-aware error toasts. */
  errorService?: ErrorHandlerService;
}

/**
 * Reusable API wrapper layer for all service calls.
 * Delegates transport/auth interceptor logic to the shared axios client
 * and centralizes error normalization plus convenience methods.
 */
class BaseApiService {
  constructor(private readonly client: AxiosInstance) {}

  /** Omit Zod-only options before passing config to axios. */
  private toAxiosConfig<D = any>(config?: BaseApiRequestConfig<D>): AxiosRequestConfig<D> {
    if (!config) return {};
    const {
      responseSchema: _omitSchema,
      suppressErrorAlert: _omitAlert,
      errorService: _omitService,
      ...rest
    } = config;
    return rest as AxiosRequestConfig<D>;
  }

  /** Merge caller headers over shared JSON defaults. */
  private withResolvedHeaders<D = any>(
    config?: BaseApiRequestConfig<D>
  ): BaseApiRequestConfig<D> {
    if (!config?.headers) {
      return config || {};
    }

    return {
      ...config,
      headers: {
        ...DEFAULT_API_HEADERS,
        ...config.headers,
      },
    };
  }

  /**
   * Normalize transport/runtime errors to a consistent Error shape.
   * Adds `status` and `response` when available for UI-level handling.
   */
  private normalizeError(error: unknown): never {
    if (error instanceof AxiosError) {
      const response = error?.response;
      const status = response?.status;
      const data = response?.data as any;
      if (response) {
        const message =
          data?.detail?.message ||
          data?.detail ||
          data?.error_msg ||
          data?.message ||
          error?.message ||
          `Request failed with status ${status ?? 'unknown'}`;
        const normalizedError = new Error(String(message));
        (normalizedError as any).status = status;
        (normalizedError as any).response = response;
        throw normalizedError;
      }

      if (error?.request) {
        throw new Error('Network error - please check your connection');
      }
    }

    throw error as Error;
  }

  /**
   * Generic request entrypoint used by all verb helpers.
   */
  async request<T = any, D = any>(
    method: Method,
    url: string,
    data?: D,
    config?: BaseApiRequestConfig<D>
  ): Promise<AxiosResponse<T>> {
    const schema = config?.responseSchema;
    try {
      const resolved = this.withResolvedHeaders(
        this.toAxiosConfig(config) as BaseApiRequestConfig<D>
      ) as AxiosRequestConfig<D>;
      const response = await this.client.request<T, AxiosResponse<T>, D>({
        ...resolved,
        method,
        url,
        data,
      });
      if (schema) {
        response.data = parseResponseData(response.data, schema, {
          method,
          url,
        }) as T;
      } else if (
        warnOnMissingResponseSchema &&
        response.status >= 200 &&
        response.status < 300
      ) {
        console.warn(`[API] Missing responseSchema for ${method} ${url}`);
      }
      return response;
    } catch (error) {
      const suppressAlert = config?.suppressErrorAlert === true;
      if (typeof window !== 'undefined' && !suppressAlert && !isCancel(error)) {
        handleApiError(error, { service: config?.errorService });
      }
      this.normalizeError(error);
    }
  }

  /** Perform a GET request. */
  get<T = any, D = any>(
    url: string,
    config?: BaseApiRequestConfig<D>
  ): Promise<AxiosResponse<T>> {
    return this.request<T, D>('GET', url, undefined, config);
  }

  /** Perform a POST request. */
  post<T = any, D = any>(
    url: string,
    data?: D,
    config?: BaseApiRequestConfig<D>
  ): Promise<AxiosResponse<T>> {
    return this.request<T, D>('POST', url, data, config);
  }

  /** Perform a PUT request. */
  put<T = any, D = any>(
    url: string,
    data?: D,
    config?: BaseApiRequestConfig<D>
  ): Promise<AxiosResponse<T>> {
    return this.request<T, D>('PUT', url, data, config);
  }

  /** Perform a DELETE request. */
  delete<T = any, D = any>(
    url: string,
    config?: BaseApiRequestConfig<D>
  ): Promise<AxiosResponse<T>> {
    return this.request<T, D>('DELETE', url, undefined, config);
  }

  /** Perform a PATCH request. */
  patch<T = any, D = any>(
    url: string,
    data?: D,
    config?: BaseApiRequestConfig<D>
  ): Promise<AxiosResponse<T>> {
    return this.request<T, D>('PATCH', url, data, config);
  }
}

export default BaseApiService;
