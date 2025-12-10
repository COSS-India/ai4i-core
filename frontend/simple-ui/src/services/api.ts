// Axios API client with interceptors for authentication and request tracking

import axios, { AxiosInstance, AxiosResponse, AxiosError } from 'axios';
import { useToast } from '@chakra-ui/react';

// API Base URL from environment.
// For production this should be set to the browser-facing API gateway URL
// (for example, https://dev.ai4inclusion.org or a dedicated API domain).
// Default to localhost:8080 for local development if not set.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL;

// Debug: Log the API base URL in development
if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
  console.log('API Base URL:', API_BASE_URL);
  console.log('NEXT_PUBLIC_API_URL from env:', process.env.NEXT_PUBLIC_API_URL);
}

// API Key from localStorage (user-provided) or environment (fallback)
const getApiKey = (): string | null => {
  if (typeof window !== 'undefined') {
    // First check localStorage (user-provided via "manage API key")
    const storedApiKey = localStorage.getItem('api_key');
    if (storedApiKey && storedApiKey.trim() !== '') {
      return storedApiKey.trim();
    }
    // Fallback to environment variable if no API key is provided
    const envApiKey = process.env.NEXT_PUBLIC_API_KEY;
    if (envApiKey && envApiKey.trim() !== '' && envApiKey !== 'your_api_key_here') {
      return envApiKey.trim();
    }
  }
  return null;
};

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
} as const;

// Create Axios instance with standard timeout
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 300000, // 5 minutes (300 seconds) for most requests
  headers: {
    'Content-Type': 'application/json',
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
  (config) => {
    config.headers['request-startTime'] = new Date().getTime().toString();
    // Use getApiKey() to respect priority: localStorage first, then env
    const apiKey = getApiKey();
    if (apiKey) {
      config.headers['Authorization'] = `Bearer ${apiKey}`;
    }
    return config;
  },
  (error) => {
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
    // Handle errors same way as apiClient
    if (error.response) {
      const { status, data } = error.response;
      if (status === 401 && typeof window !== 'undefined') {
        localStorage.removeItem('api_key');
        window.location.href = '/';
      }
    }
    return Promise.reject(error);
  }
);

// Apply same interceptors to ASR client
asrApiClient.interceptors.request.use(
  (config) => {
    config.headers['request-startTime'] = new Date().getTime().toString();
    // Use getApiKey() to respect priority: localStorage first, then env
    const apiKey = getApiKey();
    if (apiKey) {
      config.headers['Authorization'] = `Bearer ${apiKey}`;
    }
    return config;
  },
  (error) => {
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
    // Handle errors same way as apiClient
    if (error.response) {
      const { status, data } = error.response;
      if (status === 401 && typeof window !== 'undefined') {
        localStorage.removeItem('api_key');
        window.location.href = '/';
      }
    }
    return Promise.reject(error);
  }
);

// Get JWT token from auth service
const getJwtToken = (): string | null => {
  if (typeof window === 'undefined') return null;
  // Check both localStorage and sessionStorage for token (same logic as authService)
  const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token');
  return token;
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
  (config) => {
    // Add request start time for timing calculation
    config.headers['request-startTime'] = new Date().getTime().toString();
    
    // Check if this is a model-management endpoint
    const isModelManagementEndpoint = config.url?.includes('/model-management');
    
    if (isModelManagementEndpoint) {
      // For model-management endpoints, use JWT token with AUTH_TOKEN source
      const jwtToken = getJwtToken();
      if (jwtToken) {
        config.headers['Authorization'] = `Bearer ${jwtToken}`;
        config.headers['x-auth-source'] = 'AUTH_TOKEN';
      }
    } else {
      // For other endpoints, use API key if available
      const apiKey = getApiKey();
      if (apiKey) {
        config.headers['Authorization'] = `Bearer ${apiKey}`;
      }
    }
    
    return config;
  },
  (error) => {
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
            const isModelManagementEndpoint = error.config?.url?.includes('/model-management');
            
            if (isModelManagementEndpoint) {
              // For model-management endpoints, try to refresh token
              if (!originalRequest._retry) {
                originalRequest._retry = true;
                
                if (isRefreshing) {
                  // If already refreshing, queue this request
                  return new Promise((resolve, reject) => {
                    failedQueue.push({ resolve, reject });
                  })
                    .then((token) => {
                      originalRequest.headers['Authorization'] = `Bearer ${token}`;
                      return apiClient(originalRequest);
                    })
                    .catch((err) => {
                      return Promise.reject(err);
                    });
                }
                
                isRefreshing = true;
                
                try {
                  // Import authService dynamically to avoid circular dependencies
                  const { default: authService } = await import('./authService');
                  const refreshToken = authService.getRefreshToken();
                  
                  if (!refreshToken) {
                    throw new Error('No refresh token available');
                  }
                  
                  // Call refresh token API
                  const response = await authService.refreshToken();
                  const newAccessToken = response.access_token;
                  
                  // Update the token in storage
                  const rememberMe = localStorage.getItem('remember_me') === 'true';
                  authService.setAccessToken(newAccessToken, rememberMe);
                  
                  // Update the original request with new token
                  originalRequest.headers['Authorization'] = `Bearer ${newAccessToken}`;
                  
                  // Process queued requests
                  processQueue(null, newAccessToken);
                  isRefreshing = false;
                  
                  // Retry the original request
                  return apiClient(originalRequest);
                } catch (refreshError) {
                  // Refresh failed, clear tokens and logout
                  processQueue(refreshError, null);
                  isRefreshing = false;
                  
                  console.error('Token refresh failed:', refreshError);
                  
                  // Clear tokens and redirect to auth page
                  const { default: authService } = await import('./authService');
                  authService.clearAuthTokens();
                  authService.clearStoredUser();
                  
                  if (typeof window !== 'undefined') {
                    window.location.href = '/auth';
                  }
                  
                  return Promise.reject(refreshError);
                }
              } else {
                // Already retried, redirect to auth
                const { default: authService } = await import('./authService');
                authService.clearAuthTokens();
                authService.clearStoredUser();
                
                if (typeof window !== 'undefined') {
                  window.location.href = '/auth';
                }
              }
            } else {
              // For other endpoints, clear API key and redirect
              localStorage.removeItem('api_key');
              window.location.href = '/';
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