import { showGlobalToast } from '../globalToastService';
import { extractMessagesFromValue } from './extractMessages';
import { parseApiError } from './parseApiError';
import type { HandleApiErrorOptions } from './types';

let lastAlertText = '';
let lastAlertAt = 0;
const ALERT_DEDUPE_MS = 3000;

function logErrorDetails(error: unknown, parsedMessage: string): void {
  if (process.env.NODE_ENV === 'development') {
    console.error('[handleApiError]', parsedMessage, error);
  }
}

function showParsedErrorToast(
  title: string | undefined,
  message: string,
  showOnlyMessage: boolean,
  duration: number
): void {
  const toastKey = showOnlyMessage ? message : `${title ?? ''}:${message}`;
  const now = Date.now();
  if (toastKey === lastAlertText && now - lastAlertAt < ALERT_DEDUPE_MS) {
    return;
  }
  lastAlertText = toastKey;
  lastAlertAt = now;

  showGlobalToast({
    title: showOnlyMessage ? undefined : title,
    description: message,
    status: 'error',
    duration,
    isClosable: true,
  });
}

/**
 * Show a user-friendly toast for API/runtime errors using centralized parsing.
 */
export function handleApiError(error: unknown, options?: HandleApiErrorOptions): void {
  if (typeof window === 'undefined' || options?.silent) return;

  const parsed = parseApiError(error);
  const showOnlyMessage = options?.showOnlyMessage ?? false;
  const duration = options?.duration ?? 7000;
  logErrorDetails(error, parsed.message);

  if (options?.validationDisplay === 'separate') {
    const responseData = (error as { response?: { data?: unknown } })?.response?.data;
    const messages = responseData ? extractMessagesFromValue(responseData) : [];
    if (messages.length > 1) {
      messages.forEach((message) => {
        showParsedErrorToast(parsed.title, message, showOnlyMessage, duration);
      });
      return;
    }
  }

  showParsedErrorToast(parsed.title, parsed.message, showOnlyMessage, duration);
}

export { showParsedErrorToast };
