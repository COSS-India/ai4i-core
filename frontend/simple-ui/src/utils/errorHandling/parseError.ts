/**
 * Unified API error parsing — service-aware mapping + generic fallback.
 */
import { AxiosError } from 'axios';
import {
  NETWORK_ERROR_MESSAGE,
  PARSE_ERROR_MESSAGES,
} from '../../config/errorShared';
import {
  ASR_ERRORS,
  TTS_ERRORS,
  NMT_ERRORS,
  PIPELINE_ERRORS,
  COMMON_ERRORS,
  OCR_ERRORS,
  TRANSLITERATION_ERRORS,
  LANGUAGE_DETECTION_ERRORS,
  SPEAKER_DIARIZATION_ERRORS,
  AUDIO_LANGUAGE_DETECTION_ERRORS,
  NER_ERRORS,
} from '../../config/constants';
import { ApiValidationError } from '../../services/dto/apiValidationError';
import { combineMessages, extractMessagesFromValue } from './extractMessages';
import type { ToastType } from '../toast';

export type { ToastType };

export type ErrorHandlerService =
  | 'asr'
  | 'tts'
  | 'nmt'
  | 'pipeline'
  | 'ocr'
  | 'transliteration'
  | 'language-detection'
  | 'speaker-diarization'
  | 'audio-language-detection'
  | 'ner';

export interface ErrorInfo {
  title: string;
  message: string;
  showOnlyMessage?: boolean;
}

export interface ParsedError {
  title: string;
  message: string;
  statusCode: number | null;
  type: ToastType;
}

export interface ParseErrorOptions {
  service?: ErrorHandlerService;
}

export interface HandleApiErrorOptions {
  service?: ErrorHandlerService;
  showOnlyMessage?: boolean;
  silent?: boolean;
  validationDisplay?: 'combined' | 'separate';
}

type ErrorEntry = { title: string; description: string };
type ErrorCodeMap = Record<string, ErrorEntry>;

const HTTP_STATUS_TITLES: Record<number, string> = {
  400: 'Validation Error',
  401: 'Unauthorized',
  403: 'Forbidden',
  404: 'Not Found',
  409: 'Conflict',
  422: 'Validation Failed',
  429: 'Too Many Requests',
  500: 'Internal Server Error',
  503: 'Service Unavailable',
};

const UNKNOWN_ERROR_TITLE = 'Unexpected Error';
const GENERIC_FALLBACK_MESSAGE = PARSE_ERROR_MESSAGES.GENERIC_FALLBACK;
const DEFAULT_ERROR_MESSAGE = PARSE_ERROR_MESSAGES.DEFAULT;

const SERVICE_ERROR_MAP: Record<ErrorHandlerService, ErrorCodeMap> = {
  asr: ASR_ERRORS,
  tts: TTS_ERRORS,
  nmt: NMT_ERRORS,
  pipeline: PIPELINE_ERRORS,
  ocr: OCR_ERRORS,
  transliteration: TRANSLITERATION_ERRORS,
  'language-detection': LANGUAGE_DETECTION_ERRORS,
  'speaker-diarization': SPEAKER_DIARIZATION_ERRORS,
  'audio-language-detection': AUDIO_LANGUAGE_DETECTION_ERRORS,
  ner: NER_ERRORS,
};

interface AxiosLikeError {
  response?: { status?: number; data?: unknown };
  status?: number;
  message?: string;
  code?: string;
}

function getStatusCode(error: unknown): number | null {
  if (error instanceof AxiosError) return error.response?.status ?? null;
  const candidate = error as AxiosLikeError;
  if (typeof candidate.response?.status === 'number') return candidate.response.status;
  if (typeof candidate.status === 'number') return candidate.status;
  return null;
}

function getResponseData(error: unknown): unknown {
  if (error instanceof AxiosError) return error.response?.data;
  return (error as AxiosLikeError).response?.data;
}

function isNetworkError(error: unknown): boolean {
  const candidate = error as AxiosLikeError;
  const message = candidate.message ?? '';
  return (
    candidate.code === 'ECONNREFUSED' ||
    candidate.code === 'ENOTFOUND' ||
    candidate.code === 'ETIMEDOUT' ||
    candidate.code === 'ECONNABORTED' ||
    message.includes('Network Error') ||
    message.toLowerCase().includes('network') ||
    message.includes('Failed to fetch')
  );
}

function getTitleForStatusCode(statusCode: number | null | undefined): string {
  if (statusCode == null || Number.isNaN(statusCode)) return UNKNOWN_ERROR_TITLE;
  return HTTP_STATUS_TITLES[statusCode] ?? UNKNOWN_ERROR_TITLE;
}

function statusToToastType(statusCode: number | null): ToastType {
  return statusCode === 429 ? 'warning' : 'error';
}

function formatErrorCode(code: string): string {
  if (code === 'PERMISSION_DENIED' || code.includes('PERMISSION_DENIED')) {
    return 'PERMISSION DENIED';
  }
  return code
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

function resolveErrorCode(detail: Record<string, unknown>): string | null {
  const code = detail.error ?? detail.code;
  return code != null ? String(code).toUpperCase() : null;
}

function applyRateLimit(errorCode: string, detail: Record<string, unknown>, message: string): string {
  if (errorCode === 'RATE_LIMIT_EXCEEDED' && detail.retryAfter) {
    return PARSE_ERROR_MESSAGES.RATE_LIMIT_WITH_RETRY(Number(detail.retryAfter));
  }
  return message;
}

function interpolateLanguagePair(description: string, detail: Record<string, unknown>): string {
  const source = detail.sourceLanguage || detail.source || 'source';
  const target = detail.targetLanguage || detail.target || 'target';
  return description.replaceAll('{source}', String(source)).replaceAll('{target}', String(target));
}

function resolveServiceMessage(
  errorCode: string,
  detail: Record<string, unknown>,
  entry: ErrorEntry
): string {
  if (errorCode === 'LANGUAGE_PAIR_NOT_SUPPORTED' || errorCode === 'S2S_LANGUAGE_PAIR_NOT_SUPPORTED') {
    return String(detail.message || interpolateLanguagePair(entry.description, detail));
  }
  return applyRateLimit(errorCode, detail, String(detail.message || entry.description));
}

function mapKnownErrorCode(
  errorCode: string,
  detail: Record<string, unknown>,
  service?: ErrorHandlerService
): ErrorInfo | null {
  const common = COMMON_ERRORS[errorCode as keyof typeof COMMON_ERRORS];
  if (common) {
    return {
      title: common.title,
      message: String(detail.message || common.description),
      showOnlyMessage: true,
    };
  }

  if (service) {
    const serviceMap = SERVICE_ERROR_MAP[service];
    const entry = serviceMap[errorCode as keyof typeof serviceMap] as ErrorEntry | undefined;
    if (entry) {
      return {
        title: entry.title,
        message: resolveServiceMessage(errorCode, detail, entry),
        showOnlyMessage: true,
      };
    }
  }

  const asrEntry = ASR_ERRORS[errorCode as keyof typeof ASR_ERRORS];
  if (asrEntry) {
    return {
      title: asrEntry.title,
      message: applyRateLimit(errorCode, detail, String(detail.message || asrEntry.description)),
      showOnlyMessage: true,
    };
  }

  if (detail.message) {
    return {
      title: formatErrorCode(errorCode),
      message: String(detail.message),
      showOnlyMessage: true,
    };
  }

  if (errorCode === 'PERMISSION_DENIED' || errorCode.includes('PERMISSION_DENIED')) {
    return {
      title: 'PERMISSION DENIED',
      message: 'You do not have the required permissions to perform this action.',
      showOnlyMessage: true,
    };
  }

  return null;
}

function resolveDetailObjectMessage(detail: Record<string, unknown>): string | null {
  if (!detail.message) return null;
  const messages = extractMessagesFromValue(detail.message);
  return messages[0] ?? String(detail.message);
}

/**
 * Service-aware error parser (replaces extractErrorInfo).
 */
export function parseError(error: unknown, options?: ParseErrorOptions): ErrorInfo {
  const service = options?.service;
  let errorMessage = DEFAULT_ERROR_MESSAGE;
  let errorTitle = 'Error';

  if (error instanceof ApiValidationError) {
    return { title: 'API Contract Mismatch', message: error.message, showOnlyMessage: true };
  }

  const data = (error as AxiosLikeError)?.response?.data as Record<string, unknown> | undefined;

  if (data) {
    const backendMessage = (data.detail as Record<string, unknown> | undefined)?.message ?? data.message ?? data.error_msg;
    if (backendMessage && typeof backendMessage === 'string') {
      errorMessage = backendMessage;
    }

    if (Array.isArray(data.detail) && data.detail.length > 0) {
      const validationMessages = extractMessagesFromValue(data.detail);
      if (validationMessages.length > 0) {
        return {
          title: 'Validation Error',
          message: combineMessages(validationMessages),
          showOnlyMessage: true,
        };
      }
    }

    if (data.detail && typeof data.detail === 'object' && !Array.isArray(data.detail)) {
      const detail = data.detail as Record<string, unknown>;
      const parsedMessage = resolveDetailObjectMessage(detail);
      if (parsedMessage) errorMessage = parsedMessage;

      const errorCode = resolveErrorCode(detail);
      if (errorCode) {
        const mapped = mapKnownErrorCode(errorCode, detail, service);
        if (mapped) return mapped;

        if (!detail.message) {
          errorTitle =
            errorCode === 'PERMISSION_DENIED' || errorCode.includes('PERMISSION_DENIED')
              ? 'PERMISSION DENIED'
              : formatErrorCode(errorCode);
        }
      }

      if (typeof detail.hint === 'string') {
        errorMessage = errorMessage + (errorMessage.endsWith('.') ? ' ' : '. ') + detail.hint;
      }

      if (errorCode && detail.message) {
        return { title: errorTitle, message: errorMessage, showOnlyMessage: true };
      }
    } else if (typeof data.detail === 'string') {
      errorMessage = data.detail;
    } else if (data.message) {
      errorMessage = String(data.message);
    }
  }

  const detailStr = typeof data?.detail === 'string' ? data.detail : '';
  const detailObj = data?.detail;
  const detailMessage =
    typeof detailObj === 'object' && detailObj !== null && (detailObj as Record<string, unknown>).message
      ? String((detailObj as Record<string, unknown>).message)
      : '';

  const detailError = (detailObj as Record<string, unknown> | undefined)?.error;
  if (
    detailMessage.toLowerCase().includes('api key') ||
    detailError === 'API_KEY_MISSING' ||
    (detailError === 'INVALID_API_KEY' && detailMessage) ||
    (error as Error)?.message?.toLowerCase().includes('api key') ||
    detailStr.toLowerCase().includes('api key')
  ) {
    if (detailMessage.toLowerCase().includes('api key')) {
      errorMessage = detailMessage;
    } else if (detailStr.toLowerCase().includes('api key')) {
      errorMessage = detailStr;
    } else if ((error as Error)?.message?.toLowerCase().includes('api key')) {
      errorMessage = (error as Error).message;
    } else if (errorMessage === DEFAULT_ERROR_MESSAGE) {
      errorMessage = PARSE_ERROR_MESSAGES.API_KEY_REQUIRED;
    }
    return { title: errorTitle, message: errorMessage, showOnlyMessage: true };
  }

  const status = getStatusCode(error);
  if (
    (status === 500 || status === 503) &&
    typeof errorMessage === 'string' &&
    errorMessage.toLowerCase().includes('unavailable')
  ) {
    errorTitle = 'Service Unavailable';
  }

  if (status === 401 || (error as AxiosLikeError)?.status === 401 || (error as Error)?.message?.includes('401')) {
    errorTitle = 'Authentication Failed';
    errorMessage =
      (error as Error)?.message?.includes('API key') || (error as Error)?.message?.includes('api key')
        ? PARSE_ERROR_MESSAGES.API_KEY_REQUIRED
        : ASR_ERRORS.AUTH_FAILED.description;
    return { title: errorTitle, message: errorMessage, showOnlyMessage: true };
  }

  const lowerMessage = (
    errorMessage ||
    detailMessage ||
    ((error as Error)?.message && String((error as Error).message)) ||
    ''
  ).toLowerCase();

  if (status === 403) {
    const errorCode = String(
      (detailObj as Record<string, unknown> | undefined)?.error ||
        (detailObj as Record<string, unknown> | undefined)?.code ||
        ''
    ).toUpperCase();

    if (errorCode === 'TENANT_SUSPENDED' || errorCode.includes('SUSPENDED')) {
      const err = ASR_ERRORS.TENANT_SUSPENDED;
      return { title: err.title, message: err.description, showOnlyMessage: true };
    }

    if (errorCode === 'UNAUTHORIZED' || lowerMessage.includes('unauthorized') || lowerMessage.includes('permission')) {
      const err = COMMON_ERRORS.UNAUTHORIZED;
      return {
        title: err.title,
        message: errorMessage !== DEFAULT_ERROR_MESSAGE ? errorMessage : err.description,
        showOnlyMessage: true,
      };
    }
  }

  if (isNetworkError(error)) {
    const err = COMMON_ERRORS.NETWORK_ERROR;
    return { title: err.title, message: err.description, showOnlyMessage: true };
  }

  if ((error as Error)?.message && errorMessage === DEFAULT_ERROR_MESSAGE) {
    errorMessage = (error as Error).message;
  }

  return { title: errorTitle, message: errorMessage, showOnlyMessage: false };
}

/** @deprecated Use parseError */
export const extractErrorInfo = parseError;

/**
 * Generic API error parser for non-service-specific toasts.
 */
export function parseApiError(error: unknown, _options?: ParseErrorOptions): ParsedError {
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
      const detail =
        typeof responseData === 'object' &&
        responseData !== null &&
        !Array.isArray(responseData) &&
        typeof (responseData as Record<string, unknown>).detail === 'object' &&
        (responseData as Record<string, unknown>).detail !== null &&
        !Array.isArray((responseData as Record<string, unknown>).detail)
          ? ((responseData as Record<string, unknown>).detail as Record<string, unknown>)
          : null;
      if (
        detail?.code === 'ENDPOINT_VALIDATION_ERROR' &&
        typeof detail.details === 'string'
      ) {
        const message =
          typeof detail.message === 'string'
            ? detail.message
            : 'Service endpoint validation failed.';
        messages.push(`${message} ${detail.details}`);
      } else {
        messages.push(...extractMessagesFromValue(responseData));
      }
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
        title: 'Network connection lost',
        message: NETWORK_ERROR_MESSAGE,
        statusCode,
        type: 'error',
      };
    }

    return {
      title: getTitleForStatusCode(statusCode),
      message: combineMessages(messages) || GENERIC_FALLBACK_MESSAGE,
      statusCode,
      type: statusToToastType(statusCode),
    };
  } catch (parseFailure) {
    if (process.env.NODE_ENV === 'development') {
      console.error('[parseApiError] Failed to parse error:', parseFailure, error);
    }
    return {
      title: UNKNOWN_ERROR_TITLE,
      message: GENERIC_FALLBACK_MESSAGE,
      statusCode: null,
      type: 'error',
    };
  }
}

export function isPermissionDeniedError(error: unknown): boolean {
  const detail = (error as AxiosLikeError)?.response?.data as Record<string, unknown> | undefined;
  const nested = detail?.detail as Record<string, unknown> | undefined;
  const errorCode = nested?.error ?? nested?.code ?? '';
  return String(errorCode).includes('PERMISSION_DENIED');
}
