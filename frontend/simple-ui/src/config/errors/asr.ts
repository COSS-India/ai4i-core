// Service error codes and user-facing messages

/** ASR service error codes and user-facing messages */
export const ASR_ERRORS = {
  LANGUAGE_NOT_SUPPORTED: {
    title: 'Language not supported',
    description: 'Uploaded audio language doesn\'t match selected language. Upload audio in selected language.',
    action: 'Select supported language',
  },
  SERVICE_UNAVAILABLE: {
    title: 'Service unavailable',
    description: 'ASR service is temporarily unavailable. Please try again in a few minutes.',
    action: 'Retry after some time',
  },
  PROCESSING_TIMEOUT: {
    title: 'Processing timeout',
    description: 'Audio processing timed out. Please try with a shorter audio file or try again later.',
    action: 'Upload shorter file or retry',
  },
  QUOTA_EXCEEDED: {
    title: 'Quota exceeded',
    description: 'You have exceeded your usage quota for ASR service. Please contact your administrator or try again tomorrow.',
    action: 'Contact admin or wait',
  },
  MODEL_UNAVAILABLE: {
    title: 'Model not available',
    description: 'The selected ASR model is currently unavailable. Please try a different model or contact support.',
    action: 'Select different model',
  },
  RATE_LIMIT_EXCEEDED: {
    title: 'Rate limit exceeded',
    description: 'Too many requests. Please wait before trying again.',
    action: 'Wait and retry',
  },
  POOR_AUDIO_QUALITY: {
    title: 'Poor audio quality',
    description: 'Audio quality is too poor for accurate transcription. Please provide clearer audio.',
    action: 'Upload better quality audio',
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
