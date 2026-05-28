// Try-It service for anonymous access to NMT
// Allows users to try NMT service without authentication
// Rate limited to 5 requests per hour per user/IP

import { apiService } from './api';
import { apiEndpoints } from './apiEndpoints';
import { nmtInferenceResponseSchema } from './dto/schemas/inference';
import { tryItServiceListSchema } from './dto/schemas/platform';
import { NMTInferenceRequest, NMTInferenceResponse } from '../types/nmt';
import type { Service } from '../types/platform';
import { getAnonymousSessionId } from '../utils/anonymousSession';

const getTryItHeaders = () => ({
  'X-Anonymous-Session-Id': getAnonymousSessionId(),
  'X-Try-It': 'true',
});

/**
 * Try-It request payload structure
 */
export interface TryItRequest {
  service_name: 'nmt';
  payload: NMTInferenceRequest;
}

/**
 * Fetch NMT services for try-it (anonymous) users.
 * Uses the centralized try-it service-list endpoint with no auth.
 * @returns Promise with raw list of services from the API
 */
export const listTryItNMTServices = async (): Promise<Service[]> => {
  const response = await apiService.get(apiEndpoints.platform.services.tryItList, {
    params: { task_type: 'nmt' },
    headers: getTryItHeaders(),
    responseSchema: tryItServiceListSchema,
  });
  return response.data;
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
    // Strip script codes for try-it: the anonymous try-it model only accepts bare
    // language codes (e.g. "en", "hi").  Sending "en_Latn" or "hi_Deva" causes a
    // "Language-pair not supported" 400 from Triton.  Logged-in inference routes
    // through SMR which picks a model that does support script codes, so we only
    // need to sanitise the config here.
    const tryItConfig: NMTInferenceRequest['config'] = {
      ...config,
      language: {
        sourceLanguage: config.language?.sourceLanguage ?? '',
        targetLanguage: config.language?.targetLanguage ?? '',
      },
    };

    const nmtPayload: NMTInferenceRequest = {
      input: [{ source: text }],
      config: tryItConfig,
      controlConfig: {
        dataTracking: false,
      },
    };

    const tryItPayload: TryItRequest = {
      service_name: 'nmt',
      payload: nmtPayload,
    };

    const response = await apiService.post(
      apiEndpoints.platform.tryIt.execute,
      tryItPayload,
      { headers: getTryItHeaders(), responseSchema: nmtInferenceResponseSchema }
    );

    // Extract response time from headers
    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error: any) {
    console.error('Try-It NMT inference error:', error);

    if (error?.response?.status === 403 || error?.response?.status === 429) {
      // Extract message from either FastAPI format (data.detail) or APISIX gateway format (data.error_msg)
      const rawMessage: string =
        (typeof error?.response?.data?.detail === 'string' ? error?.response?.data?.detail : '') ||
        error?.response?.data?.detail?.message ||
        error?.response?.data?.error_msg ||
        error?.response?.data?.message ||
        '';

      if (
        rawMessage.toLowerCase().includes('login') ||
        rawMessage.toLowerCase().includes('rate') ||
        error?.response?.status === 429
      ) {
        throw new Error('Rate limit exceeded. You can try up to 5 translations per hour. Please sign in for unlimited access.');
      }

      throw new Error('Access denied. Please login to access this service.');
    }

    if (error?.message) {
      throw error;
    }
    throw new Error('Failed to perform translation. Please try again.');
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
    const count = parseInt(sessionStorage.getItem(key) || '0');
    const firstRequestTime = parseInt(sessionStorage.getItem(timestampKey) || '0');
    const now = Date.now();
    const oneHour = 60 * 60 * 1000;

    // Reset if more than an hour has passed
    if (now - firstRequestTime > oneHour) {
      sessionStorage.setItem(key, '0');
      sessionStorage.removeItem(timestampKey);
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
    const count = parseInt(sessionStorage.getItem(key) || '0');
    const firstRequestTime = parseInt(sessionStorage.getItem(timestampKey) || '0');
    const now = Date.now();
    const oneHour = 60 * 60 * 1000;

    // Reset if more than an hour has passed
    if (now - firstRequestTime > oneHour || !firstRequestTime) {
      sessionStorage.setItem(key, '1');
      sessionStorage.setItem(timestampKey, now.toString());
    } else {
      sessionStorage.setItem(key, (count + 1).toString());
    }
  } catch (e) {
    // Ignore sessionStorage errors
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
    const count = parseInt(sessionStorage.getItem(key) || '0');
    const firstRequestTime = parseInt(sessionStorage.getItem(timestampKey) || '0');
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
