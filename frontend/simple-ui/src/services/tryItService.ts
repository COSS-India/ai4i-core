// Try-It service for anonymous access to NMT
// Allows users to try NMT service without authentication
// Rate limited to 5 requests per hour per user/IP

import axios, { AxiosInstance } from 'axios';
import { API_BASE_URL } from './api';
import { NMTInferenceRequest, NMTInferenceResponse } from '../types/nmt';
import { getAnonymousSessionId } from '../utils/anonymousSession';

// Create a dedicated axios instance for try-it (no auth required)
const tryItClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 300000, // 5 minutes
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add request interceptor to add anonymous session ID and try-it header
tryItClient.interceptors.request.use(
  (config) => {
    // Mark request as try-it (no auth; backend may return try-it eligible services)
    config.headers['X-Try-It'] = 'true';
    // Add anonymous session ID for rate limiting
    const sessionId = getAnonymousSessionId();
    config.headers['X-Anonymous-Session-Id'] = sessionId;
    // Add request start time for timing calculation
    config.headers['request-startTime'] = new Date().getTime().toString();
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Add response interceptor for timing
tryItClient.interceptors.response.use(
  (response) => {
    const startTime = response.config.headers['request-startTime'];
    if (startTime) {
      const duration = new Date().getTime() - parseInt(startTime);
      response.headers['request-duration'] = duration.toString();
    }
    return response;
  },
  (error) => {
    return Promise.reject(error);
  }
);

/**
 * Try-It request payload structure
 */
export interface TryItRequest {
  service_name: 'nmt';
  payload: NMTInferenceRequest;
}

/**
 * Fetch NMT services for try-it (anonymous) users.
 * Uses GET /api/v1/model-management/services?task_type=nmt with X-Try-It: true (no auth).
 * @returns Promise with raw list of services from the API
 */
export const listTryItNMTServices = async (): Promise<any[]> => {
  const response = await tryItClient.get<any[]>('/api/v1/model-management/services', {
    params: { task_type: 'nmt' },
  });
  return Array.isArray(response.data) ? response.data : [];
};

/**
 * Perform NMT inference using Try-It endpoint (anonymous access)
 * Rate limited to 5 requests per hour per user/IP
 * @param text - Text to translate
 * @param config - NMT configuration
 * @returns Promise with NMT inference response and timing info
 */
export const performTryItNMTInference = async (
  text: string,
  config: NMTInferenceRequest['config']
): Promise<{ data: NMTInferenceResponse; responseTime: number }> => {
  try {
    const nmtPayload: NMTInferenceRequest = {
      input: [{ source: text }],
      config,
      controlConfig: {
        dataTracking: false,
      },
    };

    const tryItPayload: TryItRequest = {
      service_name: 'nmt',
      payload: nmtPayload,
    };

    const response = await tryItClient.post<NMTInferenceResponse>(
      '/api/v1/try-it',
      tryItPayload
    );

    // Extract response time from headers
    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error: any) {
    // Handle rate limit errors
    if (error.response?.status === 403) {
      const errorMessage = error.response?.data?.detail || '';
      if (errorMessage.includes('login')) {
        throw new Error('Rate limit exceeded. Please login to continue using the service.');
      }
    }
    
    console.error('Try-It NMT inference error:', error);
    
    // Provide user-friendly error messages
    if (error.response?.status === 429) {
      throw new Error('Too many requests. Please try again later.');
    } else if (error.response?.status === 403) {
      throw new Error('Access denied. Please login to access this service.');
    } else if (error.message) {
      throw error;
    } else {
      throw new Error('Failed to perform translation. Please try again.');
    }
  }
};

/**
 * Check if user has exceeded try-it rate limit
 * This is a client-side check to provide better UX
 * @returns boolean indicating if rate limit might be exceeded
 */
export const shouldWarnAboutRateLimit = (): boolean => {
  const key = 'tryit_request_count';
  const timestampKey = 'tryit_first_request_time';
  
  if (typeof window === 'undefined') return false;
  
  try {
    const count = parseInt(localStorage.getItem(key) || '0');
    const firstRequestTime = parseInt(localStorage.getItem(timestampKey) || '0');
    const now = Date.now();
    const oneHour = 60 * 60 * 1000;
    
    // Reset if more than an hour has passed
    if (now - firstRequestTime > oneHour) {
      localStorage.setItem(key, '0');
      localStorage.removeItem(timestampKey);
      return false;
    }
    
    // Warn if approaching limit (4 or more requests)
    return count >= 4;
  } catch (e) {
    return false;
  }
};

/**
 * Track try-it request for client-side rate limit warning
 */
export const trackTryItRequest = (): void => {
  const key = 'tryit_request_count';
  const timestampKey = 'tryit_first_request_time';
  
  if (typeof window === 'undefined') return;
  
  try {
    const count = parseInt(localStorage.getItem(key) || '0');
    const firstRequestTime = parseInt(localStorage.getItem(timestampKey) || '0');
    const now = Date.now();
    const oneHour = 60 * 60 * 1000;
    
    // Reset if more than an hour has passed
    if (now - firstRequestTime > oneHour || !firstRequestTime) {
      localStorage.setItem(key, '1');
      localStorage.setItem(timestampKey, now.toString());
    } else {
      localStorage.setItem(key, (count + 1).toString());
    }
  } catch (e) {
    // Ignore localStorage errors
  }
};

/**
 * Get remaining try-it requests count
 * @returns number of remaining requests (estimate)
 */
export const getRemainingTryItRequests = (): number => {
  const key = 'tryit_request_count';
  const timestampKey = 'tryit_first_request_time';
  const limit = 5;
  
  if (typeof window === 'undefined') return limit;
  
  try {
    const count = parseInt(localStorage.getItem(key) || '0');
    const firstRequestTime = parseInt(localStorage.getItem(timestampKey) || '0');
    const now = Date.now();
    const oneHour = 60 * 60 * 1000;
    
    // Reset if more than an hour has passed
    if (now - firstRequestTime > oneHour || !firstRequestTime) {
      return limit;
    }
    
    const remaining = Math.max(0, limit - count);
    return remaining;
  } catch (e) {
    return limit;
  }
};

