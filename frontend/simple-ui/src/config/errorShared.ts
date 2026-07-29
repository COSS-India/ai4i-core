/**
 * Shared error definitions and templates used across service error maps.
 * Keeps identical messages in one place; service maps reference these by error code key.
 */

export type ErrorEntry = {
  readonly title: string;
  readonly description: string;
  readonly action: string;
};

/** Identical across all inference services (priorities 1–2). */
export const SHARED_SERVICE_ERRORS = {
  RATE_LIMIT_EXCEEDED: {
    title: 'Rate limit exceeded',
    description: 'Too many requests. Please wait before trying again.',
    action: 'Wait and retry',
  },
  INVALID_REQUEST: {
    title: 'Invalid request',
    description: 'Invalid request parameters. Please check your input and try again.',
    action: 'Verify input parameters',
  },
  AUTH_FAILED: {
    title: 'Authentication failed',
    description: 'Authentication failed. Please log in again.',
    action: 'Re-authenticate',
  },
  TENANT_SUSPENDED: {
    title: 'Tenant suspended',
    description: 'Your account access has been suspended. Please contact support.',
    action: 'Contact support',
  },
} as const satisfies Record<string, ErrorEntry>;

/** Canonical network error message (priority 6). */
export const NETWORK_ERROR_MESSAGE =
  'Network connection lost. Please check your internet connection and try again.';

export const NETWORK_ERROR_ENTRY: ErrorEntry = {
  title: 'Network connection lost',
  description: NETWORK_ERROR_MESSAGE,
  action: 'Check connection',
};

/** Shared parse/fallback messages (priority 6–7). */
export const PARSE_ERROR_MESSAGES = {
  GENERIC_FALLBACK: 'Something went wrong. Please try again.',
  DEFAULT: 'An unexpected error occurred. Please try again.',
  API_KEY_REQUIRED: 'API key is required to access this service.',
  RATE_LIMIT_WITH_RETRY: (seconds: number): string =>
    `Too many requests. Please wait ${seconds} seconds before trying again.`,
};

/** Client-side UI messages used outside API error maps (priority 7). */
export const UI_ERROR_MESSAGES = {
  AUDIO_CONVERT_FAILED: 'Failed to convert recorded audio. Please try again.',
  AUDIO_WAV_CONVERT_FAILED: 'Failed to convert audio to WAV format. Please try again.',
  FILE_PROCESS_FAILED: 'Failed to process file. Please try again.',
  AUDIO_PLAYBACK_FAILED: 'Failed to play audio. Please try again.',
  AUDIO_DOWNLOAD_FAILED: 'Failed to download audio. Please try again.',
  PASSWORD_CHANGE_FAILED: 'Failed to change password. Please try again.',
  REGISTRATION_FAILED: 'Registration failed. Please try again.',
  AUTH_CALLBACK_FAILED: 'An error occurred during authentication. Please try again.',
  AUTH_TOKENS_MISSING: 'Missing authentication tokens. Please try again.',
  LOGIN_TOKEN_NOT_STORED: 'Access token was not stored after login. Please try again.',
  REQUEST_TIMEOUT: 'Request timeout. The server is taking too long to respond. Please try again.',
  TRY_IT_RATE_LIMIT:
    'Rate limit exceeded. You can try up to 5 translations per hour. Please sign in to get access to all services.',
  TRY_IT_TRANSLATION_FAILED: 'Failed to perform translation. Please try again.',
  TRY_IT_LOGIN_REQUIRED: 'Access denied. Please login to access this service.',
  CONSENT_REQUIRED: 'You must agree to the Terms of Service and Privacy Policy to continue.',
};

export function serviceUnavailable(serviceName: string, retryHint = 'in a few minutes'): ErrorEntry {
  return {
    title: 'Service unavailable',
    description: `${serviceName} is temporarily unavailable. Please try again ${retryHint}.`,
    action: 'Retry after some time',
  };
}

export function quotaExceeded(serviceName: string, suffix = ''): ErrorEntry {
  return {
    title: 'Quota exceeded',
    description: `You have exceeded your usage quota for ${serviceName}. Please contact your administrator${suffix}.`,
    action: 'Contact admin or wait',
  };
}

export function modelUnavailable(modelLabel: string): ErrorEntry {
  return {
    title: 'Model unavailable',
    description: `${modelLabel} is currently unavailable. Please try again later.`,
    action: 'Retry later',
  };
}

/** Shared microphone errors (speaker diarization, audio language detection, pipeline). */
export const SHARED_MIC_ERRORS = {
  MIC_PERMISSION_DENIED: {
    title: 'Microphone access denied',
    description:
      'Microphone access is required to record audio. Please allow microphone permissions in your browser settings.',
    action: 'Grant microphone permission',
  },
  MIC_NOT_FOUND: {
    title: 'Microphone not detected',
    description: 'No microphone detected. Please connect a microphone and try again.',
    action: 'Connect microphone device',
  },
} as const satisfies Record<string, ErrorEntry>;

/** Shared upload errors for audio services (speaker diarization, audio language detection). */
export const SHARED_AUDIO_UPLOAD_ERRORS = {
  FILE_TOO_LARGE: {
    title: 'File size exceeds limit',
    description: 'This file is too large to process. Please upload a smaller file.',
    action: 'Compress or trim file',
  },
  INVALID_FORMAT: {
    title: 'File format not supported',
    description: 'File format not supported. Please upload audio files in WAV or MP3 format.',
    action: 'Convert file format',
  },
} as const satisfies Record<string, ErrorEntry>;
