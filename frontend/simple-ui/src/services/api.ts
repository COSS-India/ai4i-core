// Axios API client with interceptors for authentication and request tracking

import axios, { AxiosInstance, AxiosResponse, AxiosError, InternalAxiosRequestConfig } from 'axios';
import { getStoredAccessToken } from '../utils/tokenStorage';
import { responseIndicatesTenantSuspendedOrInactive } from '../utils/tenantInactiveApiErrors';
import { apiEndpoints, API_URL_PATH_MARKERS } from './apiEndpoints';

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

export { apiEndpoints };

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

const TOKEN_EXPIRY_HINTS = [
  'expired',
  'token expired',
  'invalid token',
  'token invalid',
  'jwt expired',
  'access token expired',
];

type EndpointContext = {
  isAuthEndpoint: boolean;
  isAuthRefreshEndpoint: boolean;
  isModelManagementEndpoint: boolean;
  isMultiTenantEndpoint: boolean;
  isPolicyServiceEndpoint: boolean;
  isPolicyServiceHealthPath: boolean;
  isServiceEndpoint: boolean;
  requiresJWT: boolean;
};

const SERVICE_BASE_PATHS = [
  API_URL_PATH_MARKERS.asr,
  API_URL_PATH_MARKERS.tts,
  API_URL_PATH_MARKERS.nmt,
  API_URL_PATH_MARKERS.llm,
  API_URL_PATH_MARKERS.pipeline,
  API_URL_PATH_MARKERS.ocr,
  API_URL_PATH_MARKERS.ner,
  API_URL_PATH_MARKERS.transliteration,
  API_URL_PATH_MARKERS.languageDetection,
  API_URL_PATH_MARKERS.speakerDiarization,
  API_URL_PATH_MARKERS.languageDiarization,
  API_URL_PATH_MARKERS.audioLangDetection,
  API_URL_PATH_MARKERS.telemetry,
  API_URL_PATH_MARKERS.policyService,
];

const extractErrorMessage = (data: any, fallback: string): string => {
  if (!data) return fallback;
  if (data?.detail != null) return String(data.detail);
  if (data?.message != null) return String(data.message);
  return fallback;
};

const isTokenExpiredFromMessage = (message: string): boolean => {
  const value = message.toLowerCase();
  return TOKEN_EXPIRY_HINTS.some((hint) => value.includes(hint));
};

const clearSessionAndRedirect = async (href: '/auth' | '/') => {
  const { default: authService } = await import('./authService');
  authService.clearAuthTokens();
  authService.clearStoredUser();
  if (typeof window !== 'undefined') {
    window.location.href = href;
  }
};

const getEndpointContext = (rawUrl: string): EndpointContext => {
  const url = (rawUrl || '').toLowerCase();
  const pathNoQuery = (url.split('?')[0] || '').toLowerCase();
  const isAuthEndpoint = url.includes(API_URL_PATH_MARKERS.auth);
  const isAuthRefreshEndpoint = url.includes(API_URL_PATH_MARKERS.authRefresh);
  const isModelManagementEndpoint =
    url.includes(API_URL_PATH_MARKERS.modelManagement) ||
    url.includes(API_URL_PATH_MARKERS.v1Models) ||
    url.includes(API_URL_PATH_MARKERS.v1Services);
  const isMultiTenantEndpoint = url.includes(apiEndpoints.tenants.base);
  const isPolicyServiceEndpoint = url.includes(apiEndpoints.policy.base);
  const isPolicyServiceHealthPath = pathNoQuery.endsWith(`${apiEndpoints.policy.base}/health`);
  const isServiceEndpoint =
    SERVICE_BASE_PATHS.some((base) => url.includes(base)) ||
    isModelManagementEndpoint ||
    isMultiTenantEndpoint ||
    (isPolicyServiceEndpoint && !isPolicyServiceHealthPath);

  return {
    isAuthEndpoint,
    isAuthRefreshEndpoint,
    isModelManagementEndpoint,
    isMultiTenantEndpoint,
    isPolicyServiceEndpoint,
    isPolicyServiceHealthPath,
    isServiceEndpoint,
    requiresJWT: isServiceEndpoint,
  };
};

// Request interceptor for authentication and timing
apiClient.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    config.headers = config.headers || {};
    // Add request start time for timing calculation
    config.headers['request-startTime'] = new Date().getTime().toString();
    
    // Check endpoint type to determine authentication method (case-insensitive)
    const context = getEndpointContext(config.url || '');
    
    // Services that require JWT tokens (routed via Kong with token-validator)
    const requiresJWT = context.requiresJWT;
    
    // Proactively refresh token if it's expiring soon (skip for refresh and login endpoints)
    if ((requiresJWT || (context.isAuthEndpoint && !context.isAuthRefreshEndpoint)) && !context.isAuthRefreshEndpoint) {
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
    
    if (requiresJWT && !context.isAuthEndpoint) {
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
    // Calculate request duration
    const startTime = response.config.headers['request-startTime'];
    if (startTime) {
      const duration = new Date().getTime() - parseInt(startTime);
      response.headers['request-duration'] = duration.toString();
    }
    
    return response;
  },
  async (error: AxiosError) => {
    const originalRequest = error.config as any;
    
    // Handle different error types
    if (error.response) {
      const { status, data } = error.response;

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
            const url = error.config?.url || '';
            const context = getEndpointContext(url);
            
            if (context.isServiceEndpoint || context.isModelManagementEndpoint || context.isMultiTenantEndpoint) {
              // For service endpoints and model-management endpoints
              // Check if it's a token expiration issue - if so, redirect to sign-in
              
              // Extract error message from response for better debugging
              const errorMessage = extractErrorMessage(data, 'Authentication failed');
              
              // Check if error indicates token expiration or invalid credentials
              const errorMessageLower = errorMessage.toLowerCase();
              const isInvalidAuthCredentials = errorMessageLower.includes('invalid authentication credentials');
              const isTokenExpired = isTokenExpiredFromMessage(errorMessage) || isInvalidAuthCredentials;
              
              // Log detailed error information
              const jwtToken = getJwtToken();
              const endpointType = context.isModelManagementEndpoint ? 'model-management' : 'service';
              console.warn(`${endpointType} endpoint 401 error:`, {
                url,
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
                await clearSessionAndRedirect('/');
                return Promise.reject(new Error('Session expired. Please sign in again.'));
              }
              
              // Try to refresh token if it exists and we haven't retried yet
              if (jwtToken && !originalRequest._retry) {
                originalRequest._retry = true;
                
                try {
                  const { default: authService } = await import('./authService');
                  const refreshToken = authService.getRefreshToken();
                  
                  if (refreshToken) {
                    // Try to refresh the token
                    const response = await authService.refreshToken();
                    const newAccessToken = response.access_token;
                    const rememberMe = localStorage.getItem('remember_me') === 'true';
                    authService.setAccessToken(newAccessToken, rememberMe);
                    
                    // Retry the request with new token
                    originalRequest.headers['Authorization'] = `Bearer ${newAccessToken}`;
                    return apiClient(originalRequest);
                  }
                } catch (refreshError: any) {
                  // Refresh failed - check if it's because token expired
                  const refreshErrorMsg = (refreshError?.message || '').toLowerCase();
                  const refreshFailedDueToExpiration = refreshErrorMsg.includes('expired') ||
                                                      refreshErrorMsg.includes('invalid') ||
                                                      refreshErrorMsg.includes('401') ||
                                                      refreshErrorMsg.includes('unauthorized');
                  
                  if (refreshFailedDueToExpiration || isTokenExpired) {
                    // Token expired or invalid credentials - redirect to sign-in page
                    console.warn(`Authentication failed for ${endpointType} endpoint - redirecting to sign-in`);
                    await clearSessionAndRedirect('/auth');
                    return Promise.reject(new Error('Session expired. Please sign in again.'));
                  } else {
                    // Refresh failed for other reasons - don't logout, let UI handle it
                    console.warn(`Token refresh failed for ${endpointType} endpoint:`, refreshError);
                  }
                }
              } else if (isTokenExpired) {
                // Token expired or invalid credentials - redirect to sign-in
                console.warn(`Authentication failed for ${endpointType} endpoint - redirecting to sign-in`);
                await clearSessionAndRedirect('/auth');
                return Promise.reject(new Error('Session expired. Please sign in again.'));
              }

              // Multi-tenant APIs back the app shell; any unresolved 401 should end the session
              // instead of leaving the user on broken pages (e.g. logs, profile).
              if (context.isMultiTenantEndpoint) {
                console.warn('Multi-tenant API returned 401 — ending session');
                const { forceFrontendSessionEnd } = await import('../hooks/useAuth');
                forceFrontendSessionEnd();
                return Promise.reject(new Error('Session expired. Please sign in again.'));
              }
              
              // For non-expiration errors, don't redirect - let the UI handle the error
              let enhancedErrorMessage = errorMessage;
              if (context.isModelManagementEndpoint) {
                enhancedErrorMessage = `Model management error: ${errorMessage}. Please check your authentication and try again.`;
              } else {
                enhancedErrorMessage = `Authentication failed: ${errorMessage}. Please check your login status.`;
              }
              
              const enhancedError = new Error(enhancedErrorMessage);
              (enhancedError as any).status = 401;
              (enhancedError as any).response = error.response;
              return Promise.reject(enhancedError);
            } else {
              // For auth endpoints and other non-service endpoints
              // Check if token expired and redirect to sign-in if so
              
              // Extract error message to check for expiration
              const errorMessage = extractErrorMessage(data, '');
              
              const errorMessageLower = errorMessage.toLowerCase();
              const isTokenExpired = isTokenExpiredFromMessage(errorMessage) ||
                                   errorMessageLower.includes('invalid authentication credentials');
              
              if (!originalRequest._retry) {
                originalRequest._retry = true;
                
                try {
                  const { default: authService } = await import('./authService');
                  const refreshToken = authService.getRefreshToken();
                  
                  if (refreshToken) {
                    const response = await authService.refreshToken();
                    const newAccessToken = response.access_token;
                    const rememberMe = localStorage.getItem('remember_me') === 'true';
                    authService.setAccessToken(newAccessToken, rememberMe);
                    
                    originalRequest.headers['Authorization'] = `Bearer ${newAccessToken}`;
                    return apiClient(originalRequest);
                  }
                } catch (refreshError: any) {
                  // Refresh failed - check if it's due to expiration
                  const refreshErrorMsg = (refreshError?.message || '').toLowerCase();
                  const refreshFailedDueToExpiration = refreshErrorMsg.includes('expired') ||
                                                      refreshErrorMsg.includes('invalid') ||
                                                      refreshErrorMsg.includes('401') ||
                                                      refreshErrorMsg.includes('unauthorized');
                  
                  if (refreshFailedDueToExpiration || isTokenExpired) {
                    // Token expired - redirect to sign-in
                    console.warn('Token expired for auth endpoint - redirecting to sign-in');
                    await clearSessionAndRedirect('/auth');
                    return Promise.reject(new Error('Session expired. Please sign in again.'));
                  } else {
                    // Other refresh error - logout
                    console.error('Token refresh failed for auth endpoint:', refreshError);
                    await clearSessionAndRedirect('/');
                  }
                }
              } else {
                // Already retried - token likely expired, redirect to sign-in
                console.warn('Token refresh already attempted - redirecting to sign-in');
                await clearSessionAndRedirect('/auth');
                return Promise.reject(new Error('Session expired. Please sign in again.'));
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
    } else if (error.request) {
      // Network error
      console.error('Network error - please check your connection');
    } else {
      // Other error
      console.error('Request setup error:', error.message);
    }
    
    return Promise.reject(error);
  }
);

// Export API client and endpoints
export { apiClient, API_BASE_URL };
export default apiClient;