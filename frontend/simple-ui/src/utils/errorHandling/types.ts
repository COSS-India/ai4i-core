export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface ParsedError {
  title: string;
  message: string;
  statusCode: number | null;
  type: ToastType;
}

export interface ErrorInfo {
  title: string;
  message: string;
  showOnlyMessage?: boolean;
}

/** Loose API error response shapes encountered across backend services. */
export type APIErrorResponse =
  | string
  | null
  | undefined
  | {
      message?: unknown;
      error?: unknown;
      errors?: unknown;
      detail?: unknown;
      title?: unknown;
      description?: unknown;
      statusCode?: unknown;
      data?: unknown;
      error_msg?: unknown;
      [key: string]: unknown;
    };

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

export interface HandleApiErrorOptions {
  service?: ErrorHandlerService;
  /** When true, only the backend message is shown (no title). */
  showOnlyMessage?: boolean;
  /** Skip showing a toast (logging only). */
  silent?: boolean;
  duration?: number;
  /** How to display multiple validation errors. Defaults to `combined`. */
  validationDisplay?: 'combined' | 'separate';
}
