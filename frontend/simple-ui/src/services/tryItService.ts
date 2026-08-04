// Try-It service for anonymous access to NMT / LLM
// Allows users to try services without authentication.
// Client-side rate limit is advisory only; gateway must enforce in prod.

import { apiService } from './api';
import { apiEndpoints } from './apiEndpoints';
import { nmtInferenceResponseSchema } from './dto/schemas/inference';
import { tryItServiceListSchema } from './dto/schemas/platform';
import { NMTInferenceRequest, NMTInferenceResponse } from '../types/nmt';
import type { Service } from '../types/platform';
import { UI_ERROR_MESSAGES } from '../config/constants';
import { getAnonymousSessionId } from '../utils/anonymousSession';

/** Single source for anonymous try-it hourly limit (banner + tracker). */
export const ANONYMOUS_TRY_IT_REQUESTS_PER_HOUR = 5;

const getTryItHeaders = () => ({
  'X-Anonymous-Session-Id': getAnonymousSessionId(),
  'X-Try-It': 'true',
});

export interface TryItRequest {
  service_name: 'nmt';
  serviceId?: string;
  payload: NMTInferenceRequest;
}

type TryItSelectable = {
  isTryItDefault?: boolean;
  serviceId?: string;
  service_id?: string;
  name?: string;
};

const serviceIdOf = (service: TryItSelectable): string =>
  service.serviceId || service.service_id || '';

/**
 * AI4IDS-2704: Prefer the service flagged `isTryItDefault`; otherwise use
 * `fallbackPick` (today's deterministic pick) so Try-It never goes blank.
 * If multiple services are flagged, tie-break with lowest service id so the
 * pick does not depend on API response order. Returns at most one service.
 */
export function selectTryItDefaultService<T extends TryItSelectable>(
  services: T[],
  fallbackPick: (services: T[]) => T | undefined,
): T[] {
  if (services.length === 0) return [];
  const flagged = services.filter((s) => s.isTryItDefault === true);
  if (flagged.length > 0) {
    const picked = pickLowestServiceId(flagged);
    return picked ? [picked] : [];
  }
  const fallback = fallbackPick(services);
  return fallback ? [fallback] : [];
}

/** Stable fallback when no `isTryItDefault` is set: lowest service id. */
export function pickLowestServiceId<T extends TryItSelectable>(
  services: T[],
): T | undefined {
  if (services.length === 0) return undefined;
  return [...services].sort((a, b) =>
    serviceIdOf(a).localeCompare(serviceIdOf(b)),
  )[0];
}

/**
 * Fetch services for try-it (anonymous) users by task type(s).
 * Uses GET /services/try-it-service-list?task_types=...
 */
export const listTryItServices = async (taskType: string): Promise<Service[]> => {
  const response = await apiService.get(apiEndpoints.platform.services.tryItList, {
    params: { task_types: taskType },
    headers: getTryItHeaders(),
    responseSchema: tryItServiceListSchema,
  });
  return response.data;
};

/**
 * Fetch NMT services for try-it (anonymous) users.
 * @returns Promise with raw list of services from the API
 */
export const listTryItNMTServices = async (): Promise<Service[]> => {
  return listTryItServices('nmt');
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
      serviceId: tryItConfig.serviceId,
      payload: nmtPayload,
    };

    const response = await apiService.post(
      apiEndpoints.platform.tryIt.execute,
      tryItPayload,
      { headers: getTryItHeaders(), responseSchema: nmtInferenceResponseSchema }
    );

    // Extract response time from headers
    const responseTime = Number.parseInt(response.headers['request-duration'] || '0', 10);

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
        throw new Error(UI_ERROR_MESSAGES.TRY_IT_RATE_LIMIT);
      }

      throw new Error(UI_ERROR_MESSAGES.TRY_IT_LOGIN_REQUIRED);
    }

    if (error?.message) {
      throw error;
    }
    throw new Error(UI_ERROR_MESSAGES.TRY_IT_TRANSLATION_FAILED);
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
    const count = Number.parseInt(sessionStorage.getItem(key) || '0', 10);
    const firstRequestTime = Number.parseInt(sessionStorage.getItem(timestampKey) || '0', 10);
    const now = Date.now();
    const oneHour = 60 * 60 * 1000;

    // Reset if more than an hour has passed
    if (now - firstRequestTime > oneHour) {
      sessionStorage.setItem(key, '0');
      sessionStorage.removeItem(timestampKey);
      return false;
    }

    // Warn if approaching limit (one request left before hit)
    return count >= ANONYMOUS_TRY_IT_REQUESTS_PER_HOUR - 1;
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
    const count = Number.parseInt(sessionStorage.getItem(key) || '0', 10);
    const firstRequestTime = Number.parseInt(sessionStorage.getItem(timestampKey) || '0', 10);
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
  const limit = ANONYMOUS_TRY_IT_REQUESTS_PER_HOUR;

  if (typeof window === 'undefined') return limit;

  try {
    const count = Number.parseInt(sessionStorage.getItem(key) || '0', 10);
    const firstRequestTime = Number.parseInt(sessionStorage.getItem(timestampKey) || '0', 10);
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
