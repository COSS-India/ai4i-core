// Service error codes and user-facing messages

/** Minimum NMT text length (characters) to be considered valid */
export const MIN_NMT_TEXT_LENGTH = 2;

/** NMT (Neural Machine Translation) error codes and user-facing messages */
export const NMT_ERRORS = {
  // Input errors
  NO_TEXT_INPUT: {
    title: 'No text provided',
    description: 'Please enter text to translate.',
    action: 'Enter text',
  },
  TEXT_TOO_SHORT: {
    title: 'Text too short',
    description: 'Please provide sufficient text to translate.',
    action: 'Enter longer text',
  },
  TEXT_TOO_LONG: {
    title: 'Text exceeds limit',
    description: 'Text exceeds maximum limit. Please reduce the text length.',
    action: 'Reduce text length',
  },
  INVALID_CHARACTERS: {
    title: 'Invalid characters',
    description: 'Text contains unsupported characters. Please remove special symbols and try again.',
    action: 'Remove invalid characters',
  },
  EMPTY_INPUT: {
    title: 'Empty input',
    description: 'Text input cannot be empty. Please enter some text.',
    action: 'Enter text',
  },
  SAME_LANGUAGE_ERROR: {
    title: 'Source and target same',
    description: 'Source and target languages cannot be the same. Please select different languages.',
    action: 'Change language selection',
  },
  // Service processing errors
  LANGUAGE_PAIR_NOT_SUPPORTED: {
    title: 'Language pair not supported',
    description: 'Translation from {source} to {target} is not supported. Please check available language pairs.',
    action: 'Select supported pair',
  },
  SERVICE_UNAVAILABLE: {
    title: 'Service unavailable',
    description: 'Translation service is temporarily unavailable. Please try again in a few minutes.',
    action: 'Retry after some time',
  },
  TRANSLATION_FAILED: {
    title: 'Translation failed',
    description: 'Translation failed. Please try again.',
    action: 'Retry',
  },
  QUOTA_EXCEEDED: {
    title: 'Quota exceeded',
    description: 'You have exceeded your usage quota for translation service. Please contact your administrator.',
    action: 'Contact admin or wait',
  },
  RATE_LIMIT_EXCEEDED: {
    title: 'Rate limit exceeded',
    description: 'Too many requests. Please wait before trying again.',
    action: 'Wait and retry',
  },
  MODEL_UNAVAILABLE: {
    title: 'Model not available',
    description: 'The selected translation model is currently unavailable. Please try a different model.',
    action: 'Select different model',
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
} as const;
