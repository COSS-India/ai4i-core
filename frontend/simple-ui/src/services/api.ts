// Axios API client with interceptors for authentication and request tracking

import axios, { AxiosInstance, AxiosResponse, AxiosError } from 'axios';
import { useToast } from '@chakra-ui/react';

// API Base URL from environment.
// For production this should be set to the browser-facing API gateway URL
// (for example, https://dev.ai4inclusion.org or a dedicated API domain).
// Default to localhost:8080 for local development if not set.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

// Debug: Log the API base URL in development
if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
  console.log('API Base URL:', API_BASE_URL);
  console.log('NEXT_PUBLIC_API_URL from env:', process.env.NEXT_PUBLIC_API_URL);
}

// Get JWT access token from localStorage (stored after login)
// This is used for Authorization: Bearer header
const getAuthToken = (): string | null => {
  if (typeof window !== 'undefined') {
    const accessToken = localStorage.getItem('access_token');
    if (accessToken && accessToken.trim() !== '') {
      return accessToken.trim();
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
} as const;

// Create Axios instance with standard timeout
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000, // 30 seconds for most requests
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
    // Use JWT token from login for Authorization: Bearer header
    // Kong will validate this token via Auth Service and inject X-API-Key automatically
    const authToken = getAuthToken();
    if (authToken) {
      config.headers['Authorization'] = `Bearer ${authToken}`;
    }
    // Note: X-API-Key is now injected by Kong based on route, frontend doesn't need to send it
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
        // Clear JWT tokens on 401 (unauthorized)
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
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
    // Use JWT token from login for Authorization: Bearer header
    // Kong will validate this token via Auth Service and inject X-API-Key automatically
    const authToken = getAuthToken();
    if (authToken) {
      config.headers['Authorization'] = `Bearer ${authToken}`;
    }
    // Note: X-API-Key is now injected by Kong based on route, frontend doesn't need to send it
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
        // Clear JWT tokens on 401 (unauthorized)
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        window.location.href = '/';
      }
    }
    return Promise.reject(error);
  }
);

// Request interceptor for authentication and timing
apiClient.interceptors.request.use(
  (config) => {
    // Add request start time for timing calculation
    config.headers['request-startTime'] = new Date().getTime().toString();
    
    // Use JWT token from login for Authorization: Bearer header
    // Kong will validate this token via Auth Service and inject X-API-Key automatically
    const authToken = getAuthToken();
    if (authToken) {
      config.headers['Authorization'] = `Bearer ${authToken}`;
    }
    // Note: X-API-Key is now injected by Kong based on route, frontend doesn't need to send it
    
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
  (error: AxiosError) => {
    // Handle different error types
    if (error.response) {
      const { status, data } = error.response;
      
      switch (status) {
        case 401:
          // Unauthorized - clear JWT tokens and redirect
          if (typeof window !== 'undefined') {
            localStorage.removeItem('access_token');
            localStorage.removeItem('refresh_token');
            window.location.href = '/';
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