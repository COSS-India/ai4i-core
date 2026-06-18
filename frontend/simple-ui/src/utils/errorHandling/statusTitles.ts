import type { ToastType } from './types';

/** HTTP status code → user-facing toast title. Backend message is shown separately. */
export const HTTP_STATUS_TITLES: Record<number, string> = {
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

export const UNKNOWN_ERROR_TITLE = 'Unexpected Error';
export const GENERIC_FALLBACK_MESSAGE = 'Something went wrong. Please try again.';

export function getTitleForStatusCode(statusCode: number | null | undefined): string {
  if (statusCode == null || Number.isNaN(statusCode)) {
    return UNKNOWN_ERROR_TITLE;
  }
  return HTTP_STATUS_TITLES[statusCode] ?? UNKNOWN_ERROR_TITLE;
}

export function statusToToastType(statusCode: number | null): ToastType {
  if (statusCode === 429) return 'warning';
  return 'error';
}
