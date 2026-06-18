import { AxiosError } from 'axios';
import { ApiValidationError } from '../../services/dto/apiValidationError';
import { combineMessages, extractMessagesFromValue } from './extractMessages';
import {
  GENERIC_FALLBACK_MESSAGE,
  getTitleForStatusCode,
  statusToToastType,
} from './statusTitles';
import type { APIErrorResponse, ParsedError } from './types';

interface AxiosLikeError {
  response?: {
    status?: number;
    data?: APIErrorResponse;
  };
  status?: number;
  message?: string;
  code?: string;
}

function getStatusCode(error: unknown): number | null {
  if (error instanceof AxiosError) {
    return error.response?.status ?? null;
  }
  const candidate = error as AxiosLikeError;
  if (typeof candidate.response?.status === 'number') {
    return candidate.response.status;
  }
  if (typeof candidate.status === 'number') {
    return candidate.status;
  }
  return null;
}

function getResponseData(error: unknown): APIErrorResponse {
  if (error instanceof AxiosError) {
    return error.response?.data as APIErrorResponse;
  }
  const candidate = error as AxiosLikeError;
  return candidate.response?.data;
}

function isNetworkError(error: unknown): boolean {
  const candidate = error as AxiosLikeError;
  const code = candidate.code;
  const message = candidate.message ?? '';
  return (
    code === 'ECONNREFUSED' ||
    code === 'ENOTFOUND' ||
    code === 'ETIMEDOUT' ||
    code === 'ECONNABORTED' ||
    message.includes('Network Error') ||
    message.toLowerCase().includes('network') ||
    message.includes('Failed to fetch')
  );
}

/**
 * Centralized API error parser. Never throws.
 * Preserves backend messages exactly as received whenever possible.
 */
export function parseApiError(error: unknown): ParsedError {
  try {
    if (error instanceof ApiValidationError) {
      return {
        title: 'API Contract Mismatch',
        message: error.message,
        statusCode: null,
        type: 'error',
      };
    }

    const statusCode = getStatusCode(error);
    const responseData = getResponseData(error);
    const messages: string[] = [];

    if (responseData !== undefined) {
      messages.push(...extractMessagesFromValue(responseData));
    }

    const errorMessage = (error as Error | undefined)?.message;
    if (messages.length === 0 && errorMessage) {
      const fromMessage = extractMessagesFromValue(errorMessage);
      if (fromMessage.length > 0) {
        messages.push(...fromMessage);
      } else if (!errorMessage.startsWith('Request failed with status')) {
        messages.push(errorMessage);
      }
    }

    if (isNetworkError(error) && messages.length === 0) {
      return {
        title: 'Network Error',
        message: 'Unable to reach the server. Please check your connection and try again.',
        statusCode,
        type: 'error',
      };
    }

    const message = combineMessages(messages) || GENERIC_FALLBACK_MESSAGE;
    const title = getTitleForStatusCode(statusCode);
    const type = statusToToastType(statusCode);

    return {
      title,
      message,
      statusCode,
      type,
    };
  } catch (parseFailure) {
    if (process.env.NODE_ENV === 'development') {
      console.error('[parseApiError] Failed to parse error:', parseFailure, error);
    }
    return {
      title: 'Unexpected Error',
      message: GENERIC_FALLBACK_MESSAGE,
      statusCode: null,
      type: 'error',
    };
  }
}
