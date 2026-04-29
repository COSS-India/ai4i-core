// Axios API client with interceptors for authentication and request tracking

import axios, { AxiosInstance, AxiosResponse, AxiosError, InternalAxiosRequestConfig } from 'axios';
import { getStoredAccessToken } from '../utils/tokenStorage';
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
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (value?: any) => void;
  reject: (error?: any) => void;
}> = [];

const processQueue = (error: any, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

type EndpointContext = {
  url: string;
  isAuthEndpoint: boolean;
  isAuthRefreshEndpoint: boolean;
  isModelManagementEndpoint: boolean;
  isMultiTenantEndpoint: boolean;
  isObservabilityEndpoint: boolean;
  isServiceEndpoint: boolean;
  requiresJWT: boolean;
};

const normalizeUrl = (url?: string): string => (url || '').toLowerCase();

const getEndpointContext = (rawUrl?: string): EndpointContext => {
  const url = normalizeUrl(rawUrl);
  const pathNoQuery = (url.split('?')[0] || '').toLowerCase();
  const isTryItServiceListEndpoint = url.includes(apiEndpoints['model-management'].tryItServiceList);
  const isModelManagementEndpoint =
    url.includes(apiEndpoints['model-management'].base) && !isTryItServiceListEndpoint;
  const isASREndpoint = url.includes(apiEndpoints.asr.base);
  const isNMSEndpoint = url.includes(apiEndpoints.nmt.base);
  const isTTSEndpoint = url.includes(apiEndpoints.tts.base);
  const isLLMEndpoint = url.includes(apiEndpoints.llm.base);
  const isPipelineEndpoint = url.includes(apiEndpoints.pipeline.base);
  const isNEREndpoint = url.includes(apiEndpoints.ner.base);
  const isOCREndpoint = url.includes(apiEndpoints.ocr.base);
  const isTransliterationEndpoint = url.includes(apiEndpoints.transliteration.base);
  const isLanguageDetectionEndpoint = url.includes(apiEndpoints['language-detection'].base);
  const isSpeakerDiarizationEndpoint = url.includes(apiEndpoints['speaker-diarization'].base);
  const isLanguageDiarizationEndpoint = url.includes(apiEndpoints['language-diarization'].base);
  const isAudioLangDetectionEndpoint = url.includes(apiEndpoints['audio-language-detection'].base);
  const isObservabilityEndpoint = url.includes(apiEndpoints.telemetry.base);
  const isMultiTenantEndpoint = url.includes(apiEndpoints['multi-tenant'].base);
  const isFeatureFlagsEndpoint = url.includes(apiEndpoints['feature-flags'].base);
  const isPolicyServiceEndpoint = url.includes(apiEndpoints.policy.base);
  const isPolicyServiceHealthPath = pathNoQuery.endsWith(`${apiEndpoints.policy.base}/health`);
  const isAuthEndpoint = url.includes(apiEndpoints.auth.base);
  const isAuthRefreshEndpoint = url.includes(`${apiEndpoints.auth.base}/refresh`);

  const requiresJWT =
    isModelManagementEndpoint ||
    isASREndpoint ||
    isNMSEndpoint ||
    isTTSEndpoint ||
    isLLMEndpoint ||
    isPipelineEndpoint ||
    isAudioLangDetectionEndpoint ||
    isLanguageDetectionEndpoint ||
    isLanguageDiarizationEndpoint ||
    isSpeakerDiarizationEndpoint ||
    isNEREndpoint ||
    isOCREndpoint ||
    isTransliterationEndpoint ||
    isObservabilityEndpoint ||
    isMultiTenantEndpoint ||
    isFeatureFlagsEndpoint ||
    (isPolicyServiceEndpoint && !isPolicyServiceHealthPath);

  const isServiceEndpoint =
    isASREndpoint ||
    isTTSEndpoint ||
    isNMSEndpoint ||
    isLLMEndpoint ||
    isPipelineEndpoint ||
    isOCREndpoint ||
    isNEREndpoint ||
    isTransliterationEndpoint ||
    isLanguageDetectionEndpoint ||
    isSpeakerDiarizationEndpoint ||
    isLanguageDiarizationEndpoint ||
    isAudioLangDetectionEndpoint ||
    isObservabilityEndpoint ||
    isPolicyServiceEndpoint ||
    isModelManagementEndpoint ||
    isMultiTenantEndpoint;

  return {
    url,
    isAuthEndpoint,
    isAuthRefreshEndpoint,
    isModelManagementEndpoint,
    isMultiTenantEndpoint,
    isObservabilityEndpoint,
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
  const { default: authService } = await import('./authService');
  authService.clearAuthTokens();
  authService.clearStoredUser();
  if (typeof window !== 'undefined') {
    window.location.href = redirectPath;
  }
};

const tryRefreshAndRetry = async (originalRequest: any): Promise<AxiosResponse | null> => {
  const { default: authService } = await import('./authService');
  const refreshToken = authService.getRefreshToken();
  if (!refreshToken) return null;

  const response = await authService.refreshToken();
  const newAccessToken = response.access_token;
  const rememberMe = localStorage.getItem('remember_me') === 'true';
  authService.setAccessToken(newAccessToken, rememberMe);

  originalRequest.headers = originalRequest.headers || {};
  originalRequest.headers['Authorization'] = `Bearer ${newAccessToken}`;
  return apiClient(originalRequest);
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
        const { default: authService } = await import('./authService');
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
        const { forceFrontendSessionEnd } = await import('../hooks/useAuth');
        forceFrontendSessionEnd();
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
              // For service endpoints and model-management endpoints
              // Check if it's a token expiration issue - if so, redirect to sign-in
              const errorMessage = extractErrorMessage(data, 'Authentication failed');
              const isInvalidAuthCredentials = isInvalidAuthCredentialsMessage(errorMessage);
              const isTokenExpired = isTokenExpiredMessage(errorMessage);

              // Log detailed error information
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
              
              // If invalid authentication credentials, redirect immediately without trying to refresh
              if (isInvalidAuthCredentials) {
                console.warn(`Invalid authentication credentials for ${endpointType} endpoint - redirecting to sign-in`);
                await clearAuthAndRedirect('/');
                return Promise.reject(createSessionExpiredError());
              }

              // Try to refresh token if it exists and we haven't retried yet
              if (jwtToken && !originalRequest._retry) {
                originalRequest._retry = true;

                try {
                  const retryResponse = await tryRefreshAndRetry(originalRequest);
                  if (retryResponse) return retryResponse;
                } catch (refreshError: any) {
                  if (isAuthRefreshFailure(refreshError) || isTokenExpired) {
                    // Token expired or invalid credentials - redirect to sign-in page
                    console.warn(`Authentication failed for ${endpointType} endpoint - redirecting to sign-in`);
                    await clearAuthAndRedirect('/auth');
                    return Promise.reject(createSessionExpiredError());
                  } else {
                    // Refresh failed for other reasons - don't logout, let UI handle it
                    console.warn(`Token refresh failed for ${endpointType} endpoint:`, refreshError);
                  }
                }
              } else if (isTokenExpired) {
                // Token expired or invalid credentials - redirect to sign-in
                console.warn(`Authentication failed for ${endpointType} endpoint - redirecting to sign-in`);
                await clearAuthAndRedirect('/auth');
                return Promise.reject(createSessionExpiredError());
              }

              // Multi-tenant APIs back the app shell; any unresolved 401 should end the session
              // instead of leaving the user on broken pages (e.g. logs, profile).
              if (endpointContext.isMultiTenantEndpoint) {
                console.warn('Multi-tenant API returned 401 — ending session');
                const { forceFrontendSessionEnd } = await import('../hooks/useAuth');
                forceFrontendSessionEnd();
                return Promise.reject(createSessionExpiredError());
              }
              
              // For non-expiration errors, don't redirect - let the UI handle the error
              let enhancedErrorMessage = errorMessage;
              if (endpointContext.isModelManagementEndpoint) {
                enhancedErrorMessage = `Model management error: ${errorMessage}. Please check your authentication and try again.`;
              } else {
                enhancedErrorMessage = `Authentication failed: ${errorMessage}. Please check your login status.`;
              }
              
              const enhancedError = new Error(enhancedErrorMessage);
              (enhancedError as any).status = 401;
              (enhancedError as any).response = resolvedError.response;
              return Promise.reject(enhancedError);
            } else {
              // For auth endpoints and other non-service endpoints
              // Check if token expired and redirect to sign-in if so
              const errorMessage = extractErrorMessage(data);
              const isTokenExpired = isTokenExpiredMessage(errorMessage);
              
              if (!originalRequest._retry) {
                originalRequest._retry = true;

                try {
                  const retryResponse = await tryRefreshAndRetry(originalRequest);
                  if (retryResponse) return retryResponse;
                } catch (refreshError: any) {
                  if (isAuthRefreshFailure(refreshError) || isTokenExpired) {
                    // Token expired - redirect to sign-in
                    console.warn('Token expired for auth endpoint - redirecting to sign-in');
                    await clearAuthAndRedirect('/auth');
                    return Promise.reject(createSessionExpiredError());
                  } else {
                    // Other refresh error - logout
                    console.error('Token refresh failed for auth endpoint:', refreshError);
                    await clearAuthAndRedirect('/');
                  }
                }
              } else {
                // Already retried - token likely expired, redirect to sign-in
                console.warn('Token refresh already attempted - redirecting to sign-in');
                await clearAuthAndRedirect('/auth');
                return Promise.reject(createSessionExpiredError());
              }
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
export default apiClient;