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

export interface BaseApiRequestConfig<D = any> extends AxiosRequestConfig<D> {
  headers?: ApiRequestHeaders;
}

class BaseApiService {
  constructor(private readonly client: AxiosInstance) {}

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

  get<T = any, D = any>(
    url: string,
    config?: BaseApiRequestConfig<D>
  ): Promise<AxiosResponse<T>> {
    return this.request<T, D>('GET', url, undefined, config);
  }

  post<T = any, D = any>(
    url: string,
    data?: D,
    config?: BaseApiRequestConfig<D>
  ): Promise<AxiosResponse<T>> {
    return this.request<T, D>('POST', url, data, config);
  }

  put<T = any, D = any>(
    url: string,
    data?: D,
    config?: BaseApiRequestConfig<D>
  ): Promise<AxiosResponse<T>> {
    return this.request<T, D>('PUT', url, data, config);
  }

  delete<T = any, D = any>(
    url: string,
    config?: BaseApiRequestConfig<D>
  ): Promise<AxiosResponse<T>> {
    return this.request<T, D>('DELETE', url, undefined, config);
  }

  patch<T = any, D = any>(
    url: string,
    data?: D,
    config?: BaseApiRequestConfig<D>
  ): Promise<AxiosResponse<T>> {
    return this.request<T, D>('PATCH', url, data, config);
  }
}

export default BaseApiService;
