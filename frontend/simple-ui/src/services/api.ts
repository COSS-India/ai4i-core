// Axios API client with interceptors for authentication and request tracking

import axios, {
  AxiosInstance,
  AxiosResponse,
  AxiosError,
  InternalAxiosRequestConfig,
  AxiosRequestConfig,
  Method,
} from 'axios';
import { getStoredAccessToken, getRememberMePreference } from '../utils/tokenStorage';
import { responseIndicatesTenantSuspendedOrInactive } from '../utils/tenantInactiveApiErrors';

// API Base URL from environment.
// For production this should be set to the browser-facing API gateway URL
// (for example, https://dev.ai4inclusion.org or a dedicated API domain).
// Default to localhost:9000 for local development (docker-compose-local.yml) if not set.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ;

// Debug: Log the API base URL in development
if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
  console.log('API Base URL:', API_BASE_URL);
  console.log('NEXT_PUBLIC_API_URL from env:', process.env.NEXT_PUBLIC_API_URL);
}

import { apiEndpoints, appUrlDefaults } from './apiEndpoints';

export { apiEndpoints, appUrlDefaults };

export type ApiRequestHeaders = Record<string, string>;
const DEFAULT_API_HEADERS: ApiRequestHeaders = {
  'Content-Type': 'application/json',
  Accept: 'application/json',
};

export const resolveRequestHeaders = (
  customHeaders?: ApiRequestHeaders,
  baseHeaders?: ApiRequestHeaders
): ApiRequestHeaders => ({
  ...DEFAULT_API_HEADERS,
  ...(baseHeaders || {}),
  ...(customHeaders || {}),
});

export const resolveApiResponse = <T>(response: AxiosResponse<T>): AxiosResponse<T> => {
  console.log('API Response:', {
    url: response.config.url,
    method: response.config.method,
    status: response.status,
    data: response.data,
    headers: response.headers,
  });
  const startTimeHeader = response.config.headers?.['request-startTime'];
  const startTime = typeof startTimeHeader === 'string' ? parseInt(startTimeHeader, 10) : NaN;

  if (!Number.isNaN(startTime)) {
    const duration = Date.now() - startTime;
    response.headers['request-duration'] = duration.toString();
  }

  return response;
};

export const resolveApiError = (error: AxiosError): AxiosError => {console.log('API Error:', error); return error;}

export type ApiEnvelope<T> = {
  success?: boolean;
  data?: T;
  meta?: Record<string, unknown>;
};

export const unwrapApiData = <T>(payload: T | ApiEnvelope<T>): T => {
  if (payload && typeof payload === 'object' && 'data' in (payload as any)) {
    return ((payload as ApiEnvelope<T>).data ?? null) as T;
  }
  return payload as T;
};

// Create shared Axios instance
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 300000, // 5 minutes (300 seconds)
  headers: resolveRequestHeaders(),
});

// Get JWT token (decrypted from storage)
export const getJwtToken = (): string | null => {
  if (typeof window === 'undefined') return null;
  const token = getStoredAccessToken();
  return token && token.trim() !== '' ? token.trim() : null;
};

// Flag to prevent infinite refresh loops
type AuthServiceModule = typeof import('./authService');
let authServiceModulePromise: Promise<AuthServiceModule> | null = null;
type UseAuthModule = typeof import('../hooks/useAuth');
let useAuthModulePromise: Promise<UseAuthModule> | null = null;

const getAuthServiceModule = async (): Promise<AuthServiceModule> => {
  if (!authServiceModulePromise) {
    authServiceModulePromise = import('./authService');
  }
  return authServiceModulePromise;
};

const getUseAuthModule = async (): Promise<UseAuthModule> => {
  if (!useAuthModulePromise) {
    useAuthModulePromise = import('../hooks/useAuth');
  }
  return useAuthModulePromise;
};

type EndpointContext = {
  url: string;
  isAuthEndpoint: boolean;
  isAuthRefreshEndpoint: boolean;
  isModelManagementEndpoint: boolean;
  isMultiTenantEndpoint: boolean;
  isObservabilityEndpoint: boolean;
  isFeatureFlagsEndpoint: boolean;
  isPolicyServiceEndpoint: boolean;
  isServiceEndpoint: boolean;
  requiresJWT: boolean;
};

const normalizeUrl = (url?: string): string => (url || '').toLowerCase();

const getEndpointContext = (rawUrl?: string): EndpointContext => {
  const url = normalizeUrl(rawUrl);
  const pathNoQuery = (url.split('?')[0] || '').toLowerCase();
  const includesAny = (paths: string[]): boolean => paths.some((path) => url.includes(path));

  const isTryItServiceListEndpoint = url.includes(apiEndpoints['model-management'].tryItServiceList);
  const isModelManagementEndpoint =
    url.includes(apiEndpoints['model-management'].base) && !isTryItServiceListEndpoint;
  const isServicePathEndpoint = includesAny([
    apiEndpoints.asr.base,
    apiEndpoints.tts.base,
    apiEndpoints.nmt.base,
    apiEndpoints.llm.base,
    apiEndpoints.pipeline.base,
    apiEndpoints.ocr.base,
    apiEndpoints.ner.base,
    apiEndpoints.transliteration.base,
    apiEndpoints['language-detection'].base,
    apiEndpoints['speaker-diarization'].base,
    apiEndpoints['language-diarization'].base,
    apiEndpoints['audio-language-detection'].base,
    apiEndpoints.telemetry.base,
    apiEndpoints.policy.base,
    apiEndpoints['multi-tenant'].base,
  ]);
  const isObservabilityEndpoint = url.includes(apiEndpoints.telemetry.base);
  const isMultiTenantEndpoint = url.includes(apiEndpoints['multi-tenant'].base);
  const isFeatureFlagsEndpoint = url.includes(apiEndpoints['feature-flags'].base);
  const isPolicyServiceEndpoint = url.includes(apiEndpoints.policy.base);
  const isPolicyServiceHealthPath = pathNoQuery.endsWith(`${apiEndpoints.policy.base}/health`);
  const isAuthEndpoint = url.includes(apiEndpoints.auth.base);
  const isAuthRefreshEndpoint = url.includes(`${apiEndpoints.auth.base}/refresh`);

  const requiresJWT =
    isModelManagementEndpoint ||
    isServicePathEndpoint ||
    isFeatureFlagsEndpoint ||
    (isPolicyServiceEndpoint && !isPolicyServiceHealthPath);

  const isServiceEndpoint = isServicePathEndpoint || isModelManagementEndpoint;

  return {
    url,
    isAuthEndpoint,
    isAuthRefreshEndpoint,
    isModelManagementEndpoint,
    isMultiTenantEndpoint,
    isObservabilityEndpoint,
    isFeatureFlagsEndpoint,
    isPolicyServiceEndpoint,
    isServiceEndpoint,
    requiresJWT,
  };
};

const extractErrorMessage = (data: unknown, fallback = ''): string => {
  try {
    const errorData = data as any;
    if (errorData?.detail) return String(errorData.detail);
    if (errorData?.message) return String(errorData.message);
  } catch {
    // Ignore parsing issues and return fallback.
  }
  return fallback;
};

const isInvalidAuthCredentialsMessage = (message: string): boolean =>
  message.toLowerCase().includes('invalid authentication credentials');

const isTokenExpiredMessage = (message: string): boolean => {
  const normalized = message.toLowerCase();
  return (
    normalized.includes('expired') ||
    normalized.includes('token expired') ||
    normalized.includes('invalid token') ||
    normalized.includes('token invalid') ||
    normalized.includes('jwt expired') ||
    normalized.includes('access token expired') ||
    isInvalidAuthCredentialsMessage(normalized)
  );
};

const isAuthRefreshFailure = (refreshError: any): boolean => {
  const refreshErrorMsg = (refreshError?.message || '').toLowerCase();
  return (
    refreshErrorMsg.includes('expired') ||
    refreshErrorMsg.includes('invalid') ||
    refreshErrorMsg.includes('401') ||
    refreshErrorMsg.includes('unauthorized')
  );
};

const createSessionExpiredError = () =>
  new Error('Session expired. Please sign in again.');

const clearAuthAndRedirect = async (redirectPath: string): Promise<void> => {
  const { default: authService } = await getAuthServiceModule();
  authService.clearAuthTokens();
  authService.clearStoredUser();
  if (typeof window !== 'undefined') {
    window.location.href = redirectPath;
  }
};

const tryRefreshAndRetry = async (originalRequest: any): Promise<AxiosResponse | null> => {
  const { default: authService } = await getAuthServiceModule();
  const refreshToken = authService.getRefreshToken();
  if (!refreshToken) return null;

  const response = await authService.refreshToken();
  const newAccessToken = response.access_token;
  const rememberMe = getRememberMePreference();
  authService.setAccessToken(newAccessToken, rememberMe);

  originalRequest.headers = originalRequest.headers || {};
  originalRequest.headers['Authorization'] = `Bearer ${newAccessToken}`;
  return apiClient(originalRequest);
};

const rejectEnhanced401Error = (message: string, response: AxiosResponse): Promise<never> => {
  const enhancedError = new Error(message) as Error & { status?: number; response?: AxiosResponse };
  enhancedError.status = 401;
  enhancedError.response = response;
  return Promise.reject(enhancedError);
};

const endFrontendSession = async (): Promise<void> => {
  const { forceFrontendSessionEnd } = await getUseAuthModule();
  forceFrontendSessionEnd();
};

const redirectToAuthWithExpiredSession = async (): Promise<never> => {
  await clearAuthAndRedirect('/auth');
  return Promise.reject(createSessionExpiredError());
};

const handleServiceLikeUnauthorized = async (
  endpointContext: EndpointContext,
  data: unknown,
  originalRequest: any,
  response: AxiosResponse
): Promise<AxiosResponse | never | null> => {
  const errorMessage = extractErrorMessage(data, 'Authentication failed');
  const isInvalidAuthCredentials = isInvalidAuthCredentialsMessage(errorMessage);
  const isTokenExpired = isTokenExpiredMessage(errorMessage);
  const jwtToken = getJwtToken();
  const endpointType = endpointContext.isModelManagementEndpoint ? 'model-management' : 'service';

  console.warn(`${endpointType} endpoint 401 error:`, {
    url: endpointContext.url,
    errorMessage,
    isTokenExpired,
    isInvalidAuthCredentials,
    hasJWT: !!jwtToken,
    jwtLength: jwtToken?.length || 0,
    responseData: data,
  });

  if (isInvalidAuthCredentials) {
    console.warn(`Invalid authentication credentials for ${endpointType} endpoint - redirecting to sign-in`);
    await clearAuthAndRedirect('/');
    return Promise.reject(createSessionExpiredError());
  }

  if (jwtToken && !originalRequest._retry) {
    originalRequest._retry = true;

    try {
      const retryResponse = await tryRefreshAndRetry(originalRequest);
      if (retryResponse) return retryResponse;
    } catch (refreshError: any) {
      if (isAuthRefreshFailure(refreshError) || isTokenExpired) {
        console.warn(`Authentication failed for ${endpointType} endpoint - redirecting to sign-in`);
        return redirectToAuthWithExpiredSession();
      }
      console.warn(`Token refresh failed for ${endpointType} endpoint:`, refreshError);
    }
  } else if (isTokenExpired) {
    console.warn(`Authentication failed for ${endpointType} endpoint - redirecting to sign-in`);
    return redirectToAuthWithExpiredSession();
  }

  if (endpointContext.isMultiTenantEndpoint) {
    console.warn('Multi-tenant API returned 401 — ending session');
    await endFrontendSession();
    return Promise.reject(createSessionExpiredError());
  }

  const enhancedErrorMessage = endpointContext.isModelManagementEndpoint
    ? `Model management error: ${errorMessage}. Please check your authentication and try again.`
    : `Authentication failed: ${errorMessage}. Please check your login status.`;

  return rejectEnhanced401Error(enhancedErrorMessage, response);
};

const handleNonServiceUnauthorized = async (
  data: unknown,
  originalRequest: any
): Promise<AxiosResponse | never | null> => {
  const errorMessage = extractErrorMessage(data);
  const isTokenExpired = isTokenExpiredMessage(errorMessage);

  if (!originalRequest._retry) {
    originalRequest._retry = true;

    try {
      const retryResponse = await tryRefreshAndRetry(originalRequest);
      if (retryResponse) return retryResponse;
    } catch (refreshError: any) {
      if (isAuthRefreshFailure(refreshError) || isTokenExpired) {
        console.warn('Token expired for auth endpoint - redirecting to sign-in');
        return redirectToAuthWithExpiredSession();
      }

      console.error('Token refresh failed for auth endpoint:', refreshError);
      await clearAuthAndRedirect('/');
      return null;
    }
  } else {
    console.warn('Token refresh already attempted - redirecting to sign-in');
    return redirectToAuthWithExpiredSession();
  }

  return null;
};

// Request interceptor for authentication and timing
apiClient.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    // Add request start time for timing calculation
    config.headers['request-startTime'] = new Date().getTime().toString();
    const endpointContext = getEndpointContext(config.url);

    // Telemetry endpoints can run on a different port than the API gateway.
    // Rewrite relative telemetry URLs to the telemetry service origin (without creating a new Axios instance).
    const telemetryServiceUrl = process.env.NEXT_PUBLIC_TELEMETRY_SERVICE_URL;
    if (
      telemetryServiceUrl &&
      endpointContext.isObservabilityEndpoint &&
      typeof config.url === 'string' &&
      !config.url.startsWith('http')
    ) {
      config.url = `${telemetryServiceUrl.replace(/\/$/, '')}${config.url}`;
    }

    // Proactively refresh token if it's expiring soon (skip for refresh and login endpoints)
    if (
      (endpointContext.requiresJWT || (endpointContext.isAuthEndpoint && !endpointContext.isAuthRefreshEndpoint)) &&
      !endpointContext.isAuthRefreshEndpoint
    ) {
      try {
        const { default: authService } = await getAuthServiceModule();
        // Check if token is expiring within 5 minutes and refresh if needed
        await authService.refreshIfExpiringSoon(5);
      } catch (error) {
        // Log but don't block the request - let it try anyway
        // The response interceptor will handle 401 errors
        console.debug('Proactive token refresh check failed:', error);
      }
    }

    if (endpointContext.requiresJWT && !endpointContext.isAuthEndpoint) {
      // All service endpoints use JWT Bearer token for authentication
      const jwtToken = getJwtToken();
      if (jwtToken) {
        config.headers['Authorization'] = `Bearer ${jwtToken}`;
      } else {
        // No token available — reject request before sending to avoid
        // confusing "API key missing" errors from backend
        console.warn('No JWT token available for service endpoint:', config.url);
        return Promise.reject(new axios.Cancel(
          'Authentication required. Please sign in to continue.'
        ));
      }
    }
    
    return config;
  },
  (error: AxiosError) => {
    return Promise.reject(error);
  }
);

// Response interceptor for timing and error handling
apiClient.interceptors.response.use(
  (response: AxiosResponse) => {
    return resolveApiResponse(response);
  },
  async (error: AxiosError) => {
    const resolvedError = resolveApiError(error);
    const originalRequest = error.config as any;
    
    // Handle different error types
    if (resolvedError.response) {
      const { status, data } = resolvedError.response;

      if (
        typeof window !== 'undefined' &&
        responseIndicatesTenantSuspendedOrInactive(status, data)
      ) {
        console.warn('API: tenant suspended/deactivated or user inactive — ending session');
        await endFrontendSession();
        return Promise.reject(
          new Error('Your organization account is no longer active. Please sign in again.')
        );
      }
      
      switch (status) {
        case 401:
          // Unauthorized - handle based on endpoint type
          if (typeof window !== 'undefined') {
            const endpointContext = getEndpointContext(resolvedError.config?.url);

            if (
              endpointContext.isServiceEndpoint ||
              endpointContext.isModelManagementEndpoint ||
              endpointContext.isMultiTenantEndpoint
            ) {
              return handleServiceLikeUnauthorized(
                endpointContext,
                data,
                originalRequest,
                resolvedError.response
              );
            } else {
              const retryResponse = await handleNonServiceUnauthorized(data, originalRequest);
              if (retryResponse) return retryResponse;
            }
          }
          break;
          
        case 429:
          // Rate limit exceeded
          console.warn('Rate limit exceeded. Please try again later.');
          break;
          
        case 500:
          // Server error
          console.error('Server error occurred');
          break;
          
        default:
          console.error(`API Error ${status}:`, data);
      }
    } else if (resolvedError.request) {
      // Network error
      console.error('Network error - please check your connection');
    } else {
      // Other error
      console.error('Request setup error:', resolvedError.message);
    }
    
    return Promise.reject(resolvedError);
  }
);

// Export API client and endpoints
export { apiClient, API_BASE_URL };

/**
 * Base API wrapper: one place for typed request execution and envelope unwrapping.
 * Existing services can migrate gradually from direct apiClient calls.
 */
export const apiRequest = async <T>(
  config: AxiosRequestConfig
): Promise<T> => {
  const response = await apiClient.request<T | ApiEnvelope<T>>(config);
  return unwrapApiData(response.data);
};

const apiRequestWithMethod = async <T>(
  method: Method,
  url: string,
  data?: unknown,
  config?: AxiosRequestConfig
): Promise<T> => {
  return apiRequest<T>({
    ...(config || {}),
    method,
    url,
    data,
  });
};

export const apiGet = async <T>(
  url: string,
  config?: AxiosRequestConfig
): Promise<T> => apiRequestWithMethod<T>('GET', url, undefined, config);

export const apiPost = async <T>(
  url: string,
  data?: unknown,
  config?: AxiosRequestConfig
): Promise<T> => apiRequestWithMethod<T>('POST', url, data, config);

export const apiPut = async <T>(
  url: string,
  data?: unknown,
  config?: AxiosRequestConfig
): Promise<T> => apiRequestWithMethod<T>('PUT', url, data, config);

export const apiPatch = async <T>(
  url: string,
  data?: unknown,
  config?: AxiosRequestConfig
): Promise<T> => apiRequestWithMethod<T>('PATCH', url, data, config);

export const apiDelete = async <T>(
  url: string,
  config?: AxiosRequestConfig
): Promise<T> => apiRequestWithMethod<T>('DELETE', url, undefined, config);

export default apiClient;
