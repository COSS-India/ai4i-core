// Axios API client with interceptors for authentication and request tracking

import axios, { AxiosInstance, AxiosResponse, AxiosError, InternalAxiosRequestConfig } from 'axios';

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

// Get JWT access token from localStorage or sessionStorage (stored after login)
// This is used for Authorization: Bearer header
const getAuthToken = (): string | null => {
  if (typeof window !== 'undefined') {
    // Check both localStorage and sessionStorage (same logic as getJwtToken)
    const accessToken = localStorage.getItem('access_token') || sessionStorage.getItem('access_token');
    if (accessToken && accessToken.trim() !== '') {
      return accessToken.trim();
    }
  }
  return null;
};

// Get API key from localStorage only (user-provided via "manage API key")
// Do not use env - API key must be set by the user
const getApiKey = (): string | null => {
  if (typeof window !== 'undefined') {
    const storedApiKey = localStorage.getItem('api_key');
    if (storedApiKey && storedApiKey.trim() !== '') {
      return storedApiKey.trim();
    }
  }
  return null;
};

// Note: X-API-Key is now injected by Kong automatically based on route
// Frontend only needs to send Authorization: Bearer <token>

// API Endpoints
export const apiEndpoints = {
  asr: {
    inference: '/api/v1/asr/inference',
    models: '/api/v1/asr/models',
    health: '/api/v1/asr/health',
    streamingInfo: '/api/v1/asr/streaming/info',
    streaming:
      process.env.NEXT_PUBLIC_ASR_STREAM_URL || 'ws://localhost:8087/socket.io',
  },
  tts: {
    inference: '/api/v1/tts/inference',
    voices: '/api/v1/tts/voices',
    health: '/api/v1/tts/health',
  },
  nmt: {
    inference: '/api/v1/nmt/inference',
    models: '/api/v1/nmt/models',
    services: '/api/v1/nmt/services',
    languages: '/api/v1/nmt/languages',
    health: '/api/v1/nmt/health',
  },
  llm: {
    inference: '/api/v1/llm/inference',
    models: '/api/v1/llm/models',
    health: '/api/v1/llm/health',
  },
  ocr: {
    inference: '/api/v1/ocr/inference',
    health: '/api/v1/ocr/health',
  },
  transliteration: {
    inference: '/api/v1/transliteration/inference',
    health: '/api/v1/transliteration/health',
  },
  'language-detection': {
    inference: '/api/v1/language-detection/inference',
    health: '/api/v1/language-detection/health',
  },
  'speaker-diarization': {
    inference: '/api/v1/speaker-diarization/inference',
    health: '/api/v1/speaker-diarization/health',
  },
  'language-diarization': {
    inference: '/api/v1/language-diarization/inference',
    health: '/api/v1/language-diarization/health',
  },
  'audio-language-detection': {
    inference: '/api/v1/audio-lang-detection/inference',
    health: '/api/v1/audio-lang-detection/health',
  },
  ner: {
    inference: '/api/v1/ner/inference',
    health: '/api/v1/ner/health',
  },
} as const;

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
    const isLLMEndpoint = url.includes('/api/v1/llm');
    const isAuthEndpoint = url.includes('/api/v1/auth');
    const isAuthRefreshEndpoint = url.includes('/api/v1/auth/refresh');
    
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
      // LLM requires BOTH JWT token AND API key
      const jwtToken = getJwtToken();
      if (jwtToken) {
        config.headers['Authorization'] = `Bearer ${jwtToken}`;
    }
      
      const apiKey = getApiKey();
      if (apiKey) {
        config.headers['X-API-Key'] = apiKey;
        // Set X-Auth-Source to BOTH when both JWT and API key are present
        if (jwtToken) {
          config.headers['X-Auth-Source'] = 'BOTH';
        }
      }
    } else if (!isAuthEndpoint) {
      // For other endpoints (legacy), use API key if available
      const apiKey = getApiKey();
      if (apiKey) {
        config.headers['Authorization'] = `Bearer ${apiKey}`;
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
  (error: AxiosError) => {
    // Don't automatically logout on 401 for service endpoints
    // Let the UI handle the error and show appropriate messages
    // This prevents users from being logged out when API key is missing/invalid
    if (error.response) {
      const { status } = error.response;
      if (status === 401) {
        // Log the error but don't logout - let UI handle it
        console.warn('LLM service returned 401 - check API key and authentication');
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
    
    // ASR requires BOTH JWT token AND API key
    const authToken = getAuthToken();
    if (authToken) {
      config.headers['Authorization'] = `Bearer ${authToken}`;
    }
    // Also send API key for ASR service
    const apiKey = getApiKey();
    if (apiKey) {
      config.headers['X-API-Key'] = apiKey;
      // Set x-auth-source to BOTH when both JWT token and API key are present
      if (authToken) {
        config.headers['x-auth-source'] = 'BOTH';
        config.headers['X-Auth-Source'] = 'BOTH'; // Also set uppercase for consistency
      }
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
  (error: AxiosError) => {
    // Don't automatically logout on 401 for service endpoints
    // Let the UI handle the error and show appropriate messages
    // This prevents users from being logged out when API key is missing/invalid
    if (error.response) {
      const { status } = error.response;
      if (status === 401) {
        // Log the error but don't logout - let UI handle it
        console.warn('ASR service returned 401 - check API key and authentication');
      }
    }
    return Promise.reject(error);
  }
);

// Get JWT token from auth service
export const getJwtToken = (): string | null => {
  if (typeof window === 'undefined') return null;
  // Check both localStorage and sessionStorage for token (same logic as authService)
  const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token');
  // Return null if token is empty or whitespace
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
    const isModelManagementEndpoint = url.includes('/model-management');
    const isASREndpoint = url.includes('/api/v1/asr');
    const isNMSEndpoint = url.includes('/api/v1/nmt');
    const isTTSEndpoint = url.includes('/api/v1/tts');
    const isLLMEndpoint = url.includes('/api/v1/llm');
    const isPipelineEndpoint = url.includes('/api/v1/pipeline');
    const isNEREndpoint = url.includes('/api/v1/ner');
    const isOCREndpoint = url.includes('/api/v1/ocr');
    const isTransliterationEndpoint = url.includes('/api/v1/transliteration');
    const isLanguageDetectionEndpoint = url.includes('/api/v1/language-detection');
    const isSpeakerDiarizationEndpoint = url.includes('/api/v1/speaker-diarization');
    const isLanguageDiarizationEndpoint = url.includes('/api/v1/language-diarization');
    const isAudioLangDetectionEndpoint = url.includes('/api/v1/audio-lang-detection');
    const isObservabilityEndpoint = url.includes('/api/v1/telemetry');
    const isMultiTenantEndpoint = url.includes('/api/v1/multi-tenant');
    const isFeatureFlagsEndpoint = url.includes('/api/v1/feature-flags');
    const isAuthEndpoint = url.includes('/api/v1/auth');
    const isAuthRefreshEndpoint = url.includes('/api/v1/auth/refresh');
    
    // Services that require JWT tokens (routed via Kong with token-validator)
    const requiresJWT = isModelManagementEndpoint || isASREndpoint || isNMSEndpoint || 
                        isTTSEndpoint || isLLMEndpoint || isPipelineEndpoint ||
                        isAudioLangDetectionEndpoint || isLanguageDetectionEndpoint ||
                        isLanguageDiarizationEndpoint || isSpeakerDiarizationEndpoint ||
                        isNEREndpoint || isOCREndpoint || isTransliterationEndpoint ||
                        isObservabilityEndpoint ||
                        isMultiTenantEndpoint ||
                        isFeatureFlagsEndpoint;
    
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
      // For services that require JWT tokens, use JWT token
      const jwtToken = getJwtToken();
      const apiKey = getApiKey();
      
      // Model management endpoints support both JWT and API key authentication
      if (isModelManagementEndpoint) {
        if (jwtToken && apiKey) {
          // Both JWT and API key present - use BOTH
          config.headers['Authorization'] = `Bearer ${jwtToken}`;
          config.headers['X-API-Key'] = apiKey;
          config.headers['x-auth-source'] = 'BOTH';
          config.headers['X-Auth-Source'] = 'BOTH';
          console.log('🔐 Model-management: Sending BOTH JWT + API key', {
            url: config.url,
            hasJWT: !!jwtToken,
            hasAPIKey: !!apiKey,
            apiKeyLength: apiKey?.length || 0,
          });
        } else if (jwtToken) {
          // Only JWT token present - use AUTH_TOKEN
          config.headers['Authorization'] = `Bearer ${jwtToken}`;
          config.headers['x-auth-source'] = 'AUTH_TOKEN';
          config.headers['X-Auth-Source'] = 'AUTH_TOKEN';
          console.log('🔐 Model-management: Sending JWT only (AUTH_TOKEN)', {
            url: config.url,
            hasJWT: !!jwtToken,
            hasAPIKey: false,
            jwtLength: jwtToken?.length || 0,
          });
        } else {
          console.error('❌ Model-management: No JWT token available!', {
            url: config.url,
          });
        }
      } 
      
      // Observability endpoints use JWT token with x-auth-source: BOTH
      if (isObservabilityEndpoint) {
        if (jwtToken) {
          config.headers['Authorization'] = `Bearer ${jwtToken}`;
          config.headers['x-auth-source'] = 'BOTH';
          config.headers['X-Auth-Source'] = 'BOTH';
        }
      }

      // Multi-tenant admin endpoints require JWT token (Authorization: Bearer)
      if (isMultiTenantEndpoint) {
        if (jwtToken) {
          config.headers['Authorization'] = `Bearer ${jwtToken}`;
          config.headers['x-auth-source'] = 'AUTH_TOKEN';
          config.headers['X-Auth-Source'] = 'AUTH_TOKEN';
        } else {
          console.warn('Multi-tenant: No JWT token available', { url: config.url });
        }
      }

      // Feature-flags endpoints require JWT (gateway returns 401 without Bearer token)
      if (isFeatureFlagsEndpoint && jwtToken) {
        config.headers['Authorization'] = `Bearer ${jwtToken}`;
        config.headers['x-auth-source'] = 'AUTH_TOKEN';
        config.headers['X-Auth-Source'] = 'AUTH_TOKEN';
      }
      
      // All services require BOTH JWT token AND API key
      if (isASREndpoint || isNMSEndpoint || isTTSEndpoint || isPipelineEndpoint || isLLMEndpoint || isNEREndpoint ||
          isOCREndpoint || isTransliterationEndpoint || isLanguageDetectionEndpoint || 
          isSpeakerDiarizationEndpoint || isLanguageDiarizationEndpoint || isAudioLangDetectionEndpoint) {
        if (jwtToken) {
          config.headers['Authorization'] = `Bearer ${jwtToken}`;
        }
        const apiKey = getApiKey();
        if (apiKey) {
          config.headers['X-API-Key'] = apiKey;
          // Set X-Auth-Source to BOTH when both JWT and API key are present
          // Use lowercase to match the model-management endpoint format
          if (jwtToken) {
            config.headers['x-auth-source'] = 'BOTH';
            // Also set uppercase version for consistency
            config.headers['X-Auth-Source'] = 'BOTH';
          } else {
            // If only API key is present (shouldn't happen for these endpoints, but handle it)
            console.warn('API key present but JWT token missing for service endpoint:', config.url);
          }
        } else {
          // Log warning if API key is missing
          console.warn('API key is missing for service endpoint:', config.url);
        }
        
      }
    } else if (!isAuthEndpoint) {
      // For other endpoints (legacy), use API key if available
      const apiKey = getApiKey();
      if (apiKey) {
        // Send API key in X-API-Key header (not as Bearer token)
        config.headers['X-API-Key'] = apiKey;
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
      
      switch (status) {
        case 401:
          // Unauthorized - handle based on endpoint type
          if (typeof window !== 'undefined') {
            const url = (error.config?.url || '').toLowerCase();
            const isModelManagementEndpoint = url.includes('/model-management');
            const isMultiTenantEndpoint = url.includes('/api/v1/multi-tenant');
            
            // Check if it's a service endpoint or model-management endpoint
            // These should NOT automatically logout - let the UI handle the error
            const isServiceEndpoint = url.includes('/api/v1/asr') || 
                                     url.includes('/api/v1/tts') ||
                                     url.includes('/api/v1/nmt') ||
                                     url.includes('/api/v1/llm') ||
                                     url.includes('/api/v1/pipeline') ||
                                     url.includes('/api/v1/ocr') ||
                                     url.includes('/api/v1/ner') ||
                                     url.includes('/api/v1/transliteration') ||
                                     url.includes('/api/v1/language-detection') ||
                                     url.includes('/api/v1/speaker-diarization') ||
                                     url.includes('/api/v1/language-diarization') ||
                                     url.includes('/api/v1/audio-lang-detection') ||
                                     url.includes('/api/v1/telemetry') ||
                                     isModelManagementEndpoint ||
                                     isMultiTenantEndpoint;
            
            if (isServiceEndpoint || isModelManagementEndpoint || isMultiTenantEndpoint) {
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
              const apiKey = getApiKey();
              const endpointType = isModelManagementEndpoint ? 'model-management' : 'service';
              console.warn(`${endpointType} endpoint 401 error:`, {
                url,
                errorMessage,
                isTokenExpired,
                isInvalidAuthCredentials,
                hasJWT: !!jwtToken,
                hasAPIKey: !!apiKey,
                jwtLength: jwtToken?.length || 0,
                apiKeyLength: apiKey?.length || 0,
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
              
              // For non-expiration errors (API key issues, validation errors, etc.)
              // Don't redirect - let the UI handle the error
              let enhancedErrorMessage = errorMessage;
              if (isModelManagementEndpoint) {
                enhancedErrorMessage = `Model management error: ${errorMessage}. Please check your authentication and try again.`;
              } else if (!apiKey) {
                enhancedErrorMessage = `API key is required. Please set an API key in your profile or header.`;
              } else {
                enhancedErrorMessage = `Authentication failed: ${errorMessage}. Please check your API key and login status.`;
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