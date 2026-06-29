// Shared input, file size, and rate-limit constants

/** Default max text length for NMT, TTS, NER, transliteration, and similar services. */
export const MAX_TEXT_LENGTH = 512;

/** Max text length for LLM chat/completions (higher than other text services). */
export const MAX_LLM_TEXT_LENGTH = 50_000;

/** Minimum text length shared by inference services that require substantive input. */
export const MIN_INFERENCE_TEXT_LENGTH = 2;

/** Guest users may make this many inference requests per service per hour. */
export const GUEST_REQUESTS_PER_HOUR_PER_SERVICE = 10;

/** Anonymous try-it NMT requests allowed per hour per session/IP. */
export const TRY_IT_REQUESTS_PER_HOUR = 5;

/** Client-side warning threshold before try-it rate limit is reached. */
export const TRY_IT_RATE_LIMIT_WARN_THRESHOLD = TRY_IT_REQUESTS_PER_HOUR - 1;

/** Sliding window for per-hour rate limits (ms). */
export const RATE_LIMIT_WINDOW_MS = 60 * 60 * 1000;

/** Minimum recording duration in seconds. */
export const MIN_RECORDING_DURATION = 1;

/** Maximum recording duration in seconds. */
export const MAX_RECORDING_DURATION = 60;

/** Maximum file size for audio uploads (10 MB). */
export const MAX_AUDIO_FILE_SIZE = 10 * 1024 * 1024;

/** Maximum file size for image uploads (10 MB). */
export const MAX_IMAGE_FILE_SIZE = 10 * 1024 * 1024;

/** UI timing constants (debounce, toast, refresh intervals). */
export const TIMING = {
  TOAST: {
    SUCCESS_MS: 5000,
    ERROR_MS: 7000,
    WARNING_MS: 5000,
    INFO_MS: 4000,
    DEDUPE_MS: 3000,
  },
  SEARCH_DEBOUNCE_MS: 300,
  LOGS_AUTO_REFRESH_MS: 37_000,
  COPY_FEEDBACK_MS: 2000,
  AUTH_STATE_SETTLE_MS: 100,
} as const;

export const PAGINATION = {
  TABLE_PAGE_SIZE_OPTIONS: [10, 25, 50, 100] as const,
  DEFAULT_TABLE_PAGE_SIZE: 25,
  AUDIT_PAGE_SIZE_OPTIONS: [25, 50, 100, 200] as const,
  DEFAULT_AUDIT_PAGE_SIZE: 25,
  REGISTRY_FETCH_PAGE_SIZE: 100,
  MAX_REGISTRY_FETCH_PAGES: 500,
  USER_LIST_PAGE_SIZE: 100,
} as const;
