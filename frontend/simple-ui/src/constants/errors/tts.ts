// Service error codes and user-facing messages

/** TTS (Text-to-Speech) error codes and user-facing messages */
export const TTS_ERRORS = {
  // Input errors
  NO_TEXT_INPUT: {
    title: 'No text provided',
    description: 'Please enter text to convert to speech.',
    action: 'Enter text',
  },
  TEXT_TOO_SHORT: {
    title: 'Text too short',
    description: 'Please provide sufficient text to convert.',
    action: 'Enter longer text',
  },
  TEXT_TOO_LONG: {
    title: 'Text exceeds limit',
    description: 'Text exceeds maximum limit. Please reduce the text length.',
    action: 'Reduce text length',
  },
  INVALID_CHARACTERS: {
    title: 'Invalid characters',
    description: 'Text contains invalid characters. Please use only alphanumeric characters and punctuation.',
    action: 'Remove invalid characters',
  },
  EMPTY_INPUT: {
    title: 'Empty input',
    description: 'Text input cannot be empty. Please enter some text.',
    action: 'Enter text',
  },
  LANGUAGE_MISMATCH: {
    title: 'Language mismatch',
    description: "The text language doesn't match the selected language. Please select the correct language.",
    action: 'Select correct language',
  },
  // Service processing errors
  LANGUAGE_NOT_SUPPORTED: {
    title: 'Language not supported',
    description: 'The selected language is not supported for TTS. Please choose from: Hindi, English, Tamil, Telugu, Bengali.',
    action: 'Select supported language',
  },
  VOICE_NOT_AVAILABLE: {
    title: 'Voice not available',
    description: 'The selected voice is not available for this language. Please choose a different voice.',
    action: 'Select different voice',
  },
  SERVICE_UNAVAILABLE: {
    title: 'Service unavailable',
    description: 'TTS service is temporarily unavailable. Please try again in a few minutes.',
    action: 'Retry after some time',
  },
  PROCESSING_FAILED: {
    title: 'Processing failed',
    description: 'Failed to generate speech. Please try again.',
    action: 'Retry',
  },
  QUOTA_EXCEEDED: {
    title: 'Quota exceeded',
    description: 'You have exceeded your usage quota for TTS service. Please contact your administrator or try again tomorrow.',
    action: 'Contact admin or wait',
  },
  RATE_LIMIT_EXCEEDED: {
    title: 'Rate limit exceeded',
    description: 'Too many requests. Please wait before trying again.',
    action: 'Wait and retry',
  },
  MODEL_UNAVAILABLE: {
    title: 'Model not available',
    description: 'The selected TTS model is currently unavailable. Please try a different model.',
    action: 'Select different model',
  },
  AUDIO_GEN_FAILED: {
    title: 'Audio generation failed',
    description: 'Audio generation failed. Please try again or contact support if the issue persists.',
    action: 'Retry or contact support',
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
  // Output errors
  PLAYBACK_FAILED: {
    title: 'Audio playback failed',
    description: 'Unable to play generated audio. Please try regenerating or download the file.',
    action: 'Regenerate or download',
  },
  DOWNLOAD_FAILED: {
    title: 'Download failed',
    description: 'Failed to download audio file. Please try again.',
    action: 'Retry download',
  },
  AUDIO_FORMAT_ERROR: {
    title: 'Audio format error',
    description: 'Generated audio format is not supported by your browser. Please try downloading instead.',
    action: 'Download file',
  },
} as const;
