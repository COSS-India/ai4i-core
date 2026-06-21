/**
 * Public API for error parsing and centralized error toasts.
 */
import { extractMessagesFromValue } from './errorHandling/extractMessages';
import {
  parseError,
  parseApiError,
  type ErrorHandlerService,
  type ErrorInfo,
  type HandleApiErrorOptions,
} from './errorHandling/parseError';
import { showToast } from './toast';

export type { ErrorHandlerService, ErrorInfo, HandleApiErrorOptions };
export {
  parseError,
  parseApiError,
  extractErrorInfo,
  isPermissionDeniedError,
} from './errorHandling/parseError';

export interface ShowErrorOptions {
  service?: ErrorHandlerService;
  silent?: boolean;
  showOnlyMessage?: boolean;
  validationDisplay?: 'combined' | 'separate';
}

function logError(context: string, message: string, error: unknown): void {
  if (process.env.NODE_ENV === 'development') {
    console.error(`[${context}]`, message, error);
  }
}

/**
 * Parse an API/runtime error and show a standardized error toast.
 */
export function showError(error: unknown, options?: ShowErrorOptions): void {
  if (typeof window === 'undefined' || options?.silent) return;

  const showOnlyMessage = options?.showOnlyMessage ?? false;

  if (options?.service) {
    const { message, showOnlyMessage: parsedShowOnly } = parseError(error, {
      service: options.service,
    });
    logError('showError', message, error);
    showToast({
      type: 'error',
      message,
      messageOnly: parsedShowOnly ?? showOnlyMessage,
    });
    return;
  }

  const parsed = parseApiError(error);
  logError('showError', parsed.message, error);

  if (options?.validationDisplay === 'separate') {
    const responseData = (error as { response?: { data?: unknown } })?.response?.data;
    const messages = responseData ? extractMessagesFromValue(responseData) : [];
    if (messages.length > 1) {
      messages.forEach((message) => {
        showToast({
          type: 'error',
          message,
          messageOnly: showOnlyMessage,
        });
      });
      return;
    }
  }

  showToast({
    type: 'error',
    message: parsed.message,
    messageOnly: showOnlyMessage,
  });
}

export function handleApiError(error: unknown, options?: HandleApiErrorOptions): void {
  showError(error, options);
}

const GLOBAL_ERROR_HANDLING_KEY = '__ai4iGlobalErrorHandlingInstalled';

function formatErrorArg(arg: unknown): unknown {
  if (arg instanceof Error) return arg.message;
  return arg;
}

/**
 * Install global client-side error handling once per browser session.
 */
export function installGlobalErrorHandling(): void {
  if (typeof window === 'undefined') return;
  const win = window as Window & { [GLOBAL_ERROR_HANDLING_KEY]?: boolean };
  if (win[GLOBAL_ERROR_HANDLING_KEY]) return;
  win[GLOBAL_ERROR_HANDLING_KEY] = true;

  const originalConsoleError = console.error.bind(console);
  console.error = (...args: unknown[]) => {
    originalConsoleError(...args.map(formatErrorArg));
  };

  window.addEventListener('unhandledrejection', (event) => {
    event.preventDefault();
    handleApiError(event.reason);
  });

  window.addEventListener('error', (event) => {
    event.preventDefault();
    handleApiError(event.error ?? event.message);
  });
}
