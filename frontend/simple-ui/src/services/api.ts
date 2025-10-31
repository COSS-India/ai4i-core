// Axios API client with interceptors for authentication and request tracking

import axios, { AxiosInstance, AxiosResponse, AxiosError } from 'axios';
import { useToast } from '@chakra-ui/react';

// API Base URL from environment
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

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

// Create Axios instance
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor for authentication and timing
apiClient.interceptors.request.use(
  (config) => {
    // Add request start time for timing calculation
    config.headers['request-startTime'] = new Date().getTime().toString();
    
    // Add API key if available
    if (typeof window !== 'undefined') {
      const apiKey = localStorage.getItem('api_key');
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
export { apiClient, API_BASE_URL };
export default apiClient;