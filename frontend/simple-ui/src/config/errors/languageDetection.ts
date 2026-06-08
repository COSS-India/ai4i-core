// Service error codes and user-facing messages

/** Minimum Language Detection text length (characters) to be considered valid */
export const MIN_LANGUAGE_DETECTION_TEXT_LENGTH = 2;

/** Maximum total input length for Text Language Detection textarea */
export const MAX_LANGUAGE_DETECTION_INPUT_LENGTH = 512;

/** Language Detection error codes and user-facing messages */
export const LANGUAGE_DETECTION_ERRORS = {
  // Input Errors
  TEXT_REQUIRED: {
    title: 'No text provided',
    description: 'Please enter text to detect language.',
    action: 'Enter text',
  },
  TEXT_TOO_SHORT: {
    title: 'Text too short',
    description: 'Please provide sufficient text to detect language.',
    action: 'Enter longer text',
  },
  TEXT_TOO_LONG: {
    title: 'Text exceeds limit',
    description: `Text input is too long. Please reduce the text length.`,
    action: 'Reduce text length',
  },
  // Processing Errors
  DETECTION_FAILED: {
    title: 'Detection failed',
    description: 'Cannot detect language from the provided text. Please try with longer or more distinctive text.',
    action: 'Enter longer text',
  },
  SERVICE_UNAVAILABLE: {
    title: 'Service unavailable',
    description: 'Language detection service is temporarily unavailable. Please try again in a few minutes.',
    action: 'Retry after some time',
  },
  QUOTA_EXCEEDED: {
    title: 'Quota exceeded',
    description: 'You have exceeded your usage quota for language detection service. Please contact your administrator.',
    action: 'Contact admin or wait',
  },
  RATE_LIMIT_EXCEEDED: {
    title: 'Rate limit exceeded',
    description: 'Too many requests. Please wait before trying again.',
    action: 'Wait and retry',
  },
  MODEL_UNAVAILABLE: {
    title: 'Model unavailable',
    description: 'Language detection model is currently unavailable. Please try again later.',
    action: 'Retry later',
  },
} as const;
