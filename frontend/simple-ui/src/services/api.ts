// Axios API client with interceptors for authentication and request tracking

import axios, { AxiosInstance, AxiosResponse, AxiosError } from 'axios';
import { useToast } from '@chakra-ui/react';

// API Base URL from environment
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

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
    streaming: 'ws://localhost:8087/socket.io', // Direct WebSocket connection
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

// Request interceptor for authentication and timing
apiClient.interceptors.request.use(
  (config) => {
    // Add request start time for timing calculation
    config.headers['request-startTime'] = new Date().getTime().toString();
    
    // Add API key if available (from env or localStorage)
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
          // Unauthorized - clear API key and redirect
          if (typeof window !== 'undefined') {
            localStorage.removeItem('api_key');
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
export { apiClient, llmApiClient, API_BASE_URL };
export default apiClient;