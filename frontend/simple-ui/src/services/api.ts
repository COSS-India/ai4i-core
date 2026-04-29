// Axios API client with interceptors for authentication and request tracking

import axios, { AxiosInstance, AxiosResponse, AxiosError, InternalAxiosRequestConfig } from 'axios';
import { getStoredAccessToken } from '../utils/tokenStorage';
import { responseIndicatesTenantSuspendedOrInactive } from '../utils/tenantInactiveApiErrors';
import { apiEndpoints, API_URL_PATH_MARKERS } from './apiEndpoints';

export {
  apiEndpoints,
  API_URL_PATH_MARKERS,
  API_V1,
  INFERENCE_TRACE_PATHS,
} from './apiEndpoints';

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

// Get JWT access token (decrypted from storage)
const getAuthToken = (): string | null => {
  if (typeof window !== 'undefined') {
    const accessToken = getStoredAccessToken();
    if (accessToken && accessToken.trim() !== '') {
      return accessToken.trim();
    }
  }
  return null;
};

// Create Axios instance with standard timeout
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 300000, // 5 minutes (300 seconds) for most requests
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
});

// Create Axios instance with extended timeout for LLM requests (5 minutes)
const llmApiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 300000, // 5 minutes (300 seconds) for LLM requests
  headers: {
    'Content-Type': 'application/json',
  },
});

// Create Axios instance with extended timeout for ASR requests (5 minutes)
const asrApiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 300000, // 5 minutes (300 seconds) for ASR requests
  headers: {
    'Content-Type': 'application/json',
  },
});

// Apply same interceptors to LLM client
llmApiClient.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    // Add request start time for timing calculation
    config.headers['request-startTime'] = new Date().getTime().toString();
    
    // Check endpoint type to determine authentication method (case-insensitive)
    const url = (config.url || '').toLowerCase();
    const isLLMEndpoint = url.includes(API_URL_PATH_MARKERS.llm);
    const isAuthEndpoint = url.includes(API_URL_PATH_MARKERS.auth);
    const isAuthRefreshEndpoint = url.includes(API_URL_PATH_MARKERS.authRefresh);
    
    // Proactively refresh token if it's expiring soon
    if (isLLMEndpoint && !isAuthRefreshEndpoint) {
      try {
        const { default: authService } = await import('./authService');
        await authService.refreshIfExpiringSoon(5);
      } catch (error) {
        console.debug('Proactive token refresh check failed:', error);
      }
    }
    
    if (isLLMEndpoint && !isAuthEndpoint) {
      const jwtToken = getJwtToken();
      if (jwtToken) {
        config.headers['Authorization'] = `Bearer ${jwtToken}`;
      }
    }
    
    return config;
  },
  (error: AxiosError) => {
    return Promise.reject(error);
  }
);

llmApiClient.interceptors.response.use(
  (response: AxiosResponse) => {
    const startTime = response.config.headers['request-startTime'];
    if (startTime) {
      const duration = new Date().getTime() - parseInt(startTime);
      response.headers['request-duration'] = duration.toString();
    }
    return response;
  },
  async (error: AxiosError) => {
    if (error.response && typeof window !== 'undefined') {
      const { status, data } = error.response;
      if (responseIndicatesTenantSuspendedOrInactive(status, data)) {
        console.warn('LLM: tenant/user inactive — ending session');
        const { forceFrontendSessionEnd } = await import('../hooks/useAuth');
        forceFrontendSessionEnd();
        return Promise.reject(error);
      }
      if (status === 401) {
        console.warn('LLM service returned 401 - check authentication');
      }
    }
    return Promise.reject(error);
  }
);

// Apply same interceptors to ASR client
asrApiClient.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    config.headers['request-startTime'] = new Date().getTime().toString();
    
    // Proactively refresh token if it's expiring soon
    try {
      const { default: authService } = await import('./authService');
      await authService.refreshIfExpiringSoon(5);
    } catch (error) {
      console.debug('Proactive token refresh check failed:', error);
    }
    
    const authToken = getAuthToken();
    if (authToken) {
      config.headers['Authorization'] = `Bearer ${authToken}`;
    }
    
    return config;
  },
  (error: AxiosError) => {
    return Promise.reject(error);
  }
);

asrApiClient.interceptors.response.use(
  (response: AxiosResponse) => {
    const startTime = response.config.headers['request-startTime'];
    if (startTime) {
      const duration = new Date().getTime() - parseInt(startTime);
      response.headers['request-duration'] = duration.toString();
    }
    return response;
  },
  async (error: AxiosError) => {
    if (error.response && typeof window !== 'undefined') {
      const { status, data } = error.response;
      if (responseIndicatesTenantSuspendedOrInactive(status, data)) {
        console.warn('ASR: tenant/user inactive — ending session');
        const { forceFrontendSessionEnd } = await import('../hooks/useAuth');
        forceFrontendSessionEnd();
        return Promise.reject(error);
      }
      if (status === 401) {
        console.warn('ASR service returned 401 - check authentication');
      }
    }
    return Promise.reject(error);
  }
);

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

// Request interceptor for authentication and timing
apiClient.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    // Add request start time for timing calculation
    config.headers['request-startTime'] = new Date().getTime().toString();
    
    // Check endpoint type to determine authentication method (case-insensitive)
    const url = (config.url || '').toLowerCase();
    const isModelManagementEndpoint =
      url.includes(API_URL_PATH_MARKERS.modelManagement) ||
      url.includes(API_URL_PATH_MARKERS.v1Models) ||
      url.includes(API_URL_PATH_MARKERS.v1Services);
    const isASREndpoint = url.includes(API_URL_PATH_MARKERS.asr);
    const isNMSEndpoint = url.includes(API_URL_PATH_MARKERS.nmt);
    const isTTSEndpoint = url.includes(API_URL_PATH_MARKERS.tts);
    const isLLMEndpoint = url.includes(API_URL_PATH_MARKERS.llm);
    const isPipelineEndpoint = url.includes(API_URL_PATH_MARKERS.pipeline);
    const isNEREndpoint = url.includes(API_URL_PATH_MARKERS.ner);
    const isOCREndpoint = url.includes(API_URL_PATH_MARKERS.ocr);
    const isTransliterationEndpoint = url.includes(API_URL_PATH_MARKERS.transliteration);
    const isLanguageDetectionEndpoint = url.includes(API_URL_PATH_MARKERS.languageDetection);
    const isSpeakerDiarizationEndpoint = url.includes(API_URL_PATH_MARKERS.speakerDiarization);
    const isLanguageDiarizationEndpoint = url.includes(API_URL_PATH_MARKERS.languageDiarization);
    const isAudioLangDetectionEndpoint = url.includes(API_URL_PATH_MARKERS.audioLangDetection);
    const isObservabilityEndpoint = url.includes(API_URL_PATH_MARKERS.telemetry);
    const isTenantsEndpoint = url.includes(API_URL_PATH_MARKERS.tenants);
    const isFeatureFlagsEndpoint = url.includes(API_URL_PATH_MARKERS.featureFlags);
    const isPolicyServiceEndpoint = url.includes(API_URL_PATH_MARKERS.policyService);
    const pathNoQuery = (url.split('?')[0] || '').toLowerCase();
    const isPolicyServiceHealthPath = pathNoQuery.endsWith(apiEndpoints.policy.health);
    const isAuthEndpoint = url.includes(API_URL_PATH_MARKERS.auth);
    const isAuthRefreshEndpoint = url.includes(API_URL_PATH_MARKERS.authRefresh);
    
    // Services that require JWT tokens (routed via Kong with token-validator)
    const requiresJWT = isModelManagementEndpoint || isASREndpoint || isNMSEndpoint || 
                        isTTSEndpoint || isLLMEndpoint || isPipelineEndpoint ||
                        isAudioLangDetectionEndpoint || isLanguageDetectionEndpoint ||
                        isLanguageDiarizationEndpoint || isSpeakerDiarizationEndpoint ||
                        isNEREndpoint || isOCREndpoint || isTransliterationEndpoint ||
                        isObservabilityEndpoint ||
                        isTenantsEndpoint ||
                        isFeatureFlagsEndpoint ||
                        (isPolicyServiceEndpoint && !isPolicyServiceHealthPath);
    
    // Proactively refresh token if it's expiring soon (skip for refresh and login endpoints)
    if ((requiresJWT || (isAuthEndpoint && !isAuthRefreshEndpoint)) && !isAuthRefreshEndpoint) {
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
    
    if (requiresJWT && !isAuthEndpoint) {
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
            const url = (error.config?.url || '').toLowerCase();
            const isModelManagementEndpoint =
              url.includes(API_URL_PATH_MARKERS.modelManagement) ||
              url.includes(API_URL_PATH_MARKERS.v1Models) ||
              url.includes(API_URL_PATH_MARKERS.v1Services);
            const isTenantsEndpoint = url.includes(API_URL_PATH_MARKERS.tenants);
            
            // Check if it's a service endpoint or model-management endpoint
            // These should NOT automatically logout - let the UI handle the error
            const isServiceEndpoint = url.includes(API_URL_PATH_MARKERS.asr) || 
                                     url.includes(API_URL_PATH_MARKERS.tts) ||
                                     url.includes(API_URL_PATH_MARKERS.nmt) ||
                                     url.includes(API_URL_PATH_MARKERS.llm) ||
                                     url.includes(API_URL_PATH_MARKERS.pipeline) ||
                                     url.includes(API_URL_PATH_MARKERS.ocr) ||
                                     url.includes(API_URL_PATH_MARKERS.ner) ||
                                     url.includes(API_URL_PATH_MARKERS.transliteration) ||
                                     url.includes(API_URL_PATH_MARKERS.languageDetection) ||
                                     url.includes(API_URL_PATH_MARKERS.speakerDiarization) ||
                                     url.includes(API_URL_PATH_MARKERS.languageDiarization) ||
                                     url.includes(API_URL_PATH_MARKERS.audioLangDetection) ||
                                     url.includes(API_URL_PATH_MARKERS.telemetry) ||
                                     url.includes(API_URL_PATH_MARKERS.policyService) ||
                                     isModelManagementEndpoint ||
                                     isTenantsEndpoint;
            
            if (isServiceEndpoint || isModelManagementEndpoint || isTenantsEndpoint) {
              // For service endpoints and model-management endpoints
              // Check if it's a token expiration issue - if so, redirect to sign-in
              
              // Extract error message from response for better debugging
              let errorMessage = 'Authentication failed';
              try {
                const errorData = (data as any);
                if (errorData?.detail) {
                  errorMessage = String(errorData.detail);
                } else if (errorData?.message) {
                  errorMessage = String(errorData.message);
                }
              } catch (e) {
                // Ignore parsing errors
              }
              
              // Check if error indicates token expiration or invalid credentials
              const errorMessageLower = errorMessage.toLowerCase();
              const isInvalidAuthCredentials = errorMessageLower.includes('invalid authentication credentials');
              const isTokenExpired = errorMessageLower.includes('expired') ||
                                   errorMessageLower.includes('token expired') ||
                                   errorMessageLower.includes('invalid token') ||
                                   errorMessageLower.includes('token invalid') ||
                                   errorMessageLower.includes('jwt expired') ||
                                   errorMessageLower.includes('access token expired') ||
                                   isInvalidAuthCredentials;
              
              // Log detailed error information
              const jwtToken = getJwtToken();
              const endpointType = isModelManagementEndpoint ? 'model-management' : 'service';
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
                const { default: authService } = await import('./authService');
                authService.clearAuthTokens();
                authService.clearStoredUser();
                
                if (typeof window !== 'undefined') {
                  window.location.href = '/';
                }
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
                    const { default: authService } = await import('./authService');
                    authService.clearAuthTokens();
                    authService.clearStoredUser();
                    
                    if (typeof window !== 'undefined') {
                      window.location.href = '/auth';
                    }
                    return Promise.reject(new Error('Session expired. Please sign in again.'));
                  } else {
                    // Refresh failed for other reasons - don't logout, let UI handle it
                    console.warn(`Token refresh failed for ${endpointType} endpoint:`, refreshError);
                  }
                }
              } else if (isTokenExpired) {
                // Token expired or invalid credentials - redirect to sign-in
                console.warn(`Authentication failed for ${endpointType} endpoint - redirecting to sign-in`);
                const { default: authService } = await import('./authService');
                authService.clearAuthTokens();
                authService.clearStoredUser();
                
                if (typeof window !== 'undefined') {
                  window.location.href = '/auth';
                }
                return Promise.reject(new Error('Session expired. Please sign in again.'));
              }

              // Tenant APIs back the app shell; any unresolved 401 should end the session
              // instead of leaving the user on broken pages (e.g. logs, profile).
              if (isTenantsEndpoint) {
                console.warn('Tenant API returned 401 — ending session');
                const { forceFrontendSessionEnd } = await import('../hooks/useAuth');
                forceFrontendSessionEnd();
                return Promise.reject(new Error('Session expired. Please sign in again.'));
              }
              
              // For non-expiration errors, don't redirect - let the UI handle the error
              let enhancedErrorMessage = errorMessage;
              if (isModelManagementEndpoint) {
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
              let errorMessage = '';
              try {
                const errorData = (data as any);
                if (errorData?.detail) {
                  errorMessage = String(errorData.detail);
                } else if (errorData?.message) {
                  errorMessage = String(errorData.message);
                }
              } catch (e) {
                // Ignore parsing errors
              }
              
              const errorMessageLower = errorMessage.toLowerCase();
              const isTokenExpired = errorMessageLower.includes('expired') ||
                                   errorMessageLower.includes('token expired') ||
                                   errorMessageLower.includes('invalid token') ||
                                   errorMessageLower.includes('token invalid') ||
                                   errorMessageLower.includes('jwt expired') ||
                                   errorMessageLower.includes('access token expired') ||
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
                    const { default: authService } = await import('./authService');
                    authService.clearAuthTokens();
                    authService.clearStoredUser();
                    
                    if (typeof window !== 'undefined') {
                      window.location.href = '/auth';
                    }
                    return Promise.reject(new Error('Session expired. Please sign in again.'));
                  } else {
                    // Other refresh error - logout
                    console.error('Token refresh failed for auth endpoint:', refreshError);
                    const { default: authService } = await import('./authService');
                    authService.clearAuthTokens();
                    authService.clearStoredUser();
                    
                    if (typeof window !== 'undefined') {
                      window.location.href = '/';
                    }
                  }
                }
              } else {
                // Already retried - token likely expired, redirect to sign-in
                console.warn('Token refresh already attempted - redirecting to sign-in');
                const { default: authService } = await import('./authService');
                authService.clearAuthTokens();
                authService.clearStoredUser();
                
                if (typeof window !== 'undefined') {
                  window.location.href = '/auth';
                }
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
export { apiClient, llmApiClient, asrApiClient, API_BASE_URL };
export default apiClient;
