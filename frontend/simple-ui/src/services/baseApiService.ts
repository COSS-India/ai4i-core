import {
  AxiosError,
  AxiosInstance,
  AxiosRequestConfig,
  AxiosResponse,
  Method,
} from 'axios';

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
}

/**
 * Reusable API wrapper layer for all service calls.
 * Delegates transport/auth interceptor logic to the shared axios client
 * and centralizes error normalization plus convenience methods.
 */
class BaseApiService {
  constructor(private readonly client: AxiosInstance) {}

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
      if (error.response) {
        const status = error.response.status;
        const data = error.response.data as any;
        const message =
          data?.detail?.message ||
          data?.detail ||
          data?.message ||
          error.message ||
          `Request failed with status ${status}`;
        const normalizedError = new Error(String(message));
        (normalizedError as any).status = status;
        (normalizedError as any).response = error.response;
        throw normalizedError;
      }

      if (error.request) {
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
    try {
      return await this.client.request<T, AxiosResponse<T>, D>({
        ...(this.withResolvedHeaders(config) as AxiosRequestConfig<D>),
        method,
        url,
        data,
      });
    } catch (error) {
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
