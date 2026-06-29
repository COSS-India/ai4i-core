// Service error codes and user-facing messages

import {
  SHARED_SERVICE_ERRORS,
  quotaExceeded,
  serviceUnavailable,
} from "../errorShared";

export const ASR_ERRORS = {
  LANGUAGE_NOT_SUPPORTED: {
    title: 'Language not supported',
    description: 'Uploaded audio language doesn\'t match selected language. Upload audio in selected language.',
    action: 'Select supported language',
  },
  SERVICE_UNAVAILABLE: serviceUnavailable('ASR service'),
  PROCESSING_TIMEOUT: {
    title: 'Processing timeout',
    description: 'Audio processing timed out. Please try with a shorter audio file or try again later.',
    action: 'Upload shorter file or retry',
  },
  QUOTA_EXCEEDED: quotaExceeded('ASR service', ' or try again tomorrow'),
  MODEL_UNAVAILABLE: {
    title: 'Model not available',
    description: 'The selected ASR model is currently unavailable. Please try a different model or contact support.',
    action: 'Select different model',
  },
  RATE_LIMIT_EXCEEDED: SHARED_SERVICE_ERRORS.RATE_LIMIT_EXCEEDED,
  POOR_AUDIO_QUALITY: {
    title: 'Poor audio quality',
    description: 'Audio quality is too poor for accurate transcription. Please provide clearer audio.',
    action: 'Upload better quality audio',
  },
  INVALID_REQUEST: SHARED_SERVICE_ERRORS.INVALID_REQUEST,
  AUTH_FAILED: SHARED_SERVICE_ERRORS.AUTH_FAILED,
  TENANT_SUSPENDED: SHARED_SERVICE_ERRORS.TENANT_SUSPENDED,
} as const;
