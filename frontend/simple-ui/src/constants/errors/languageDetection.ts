// Service error codes and user-facing messages

import {
  SHARED_SERVICE_ERRORS,
  modelUnavailable,
  quotaExceeded,
  serviceUnavailable,
} from "../errorShared";

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
  SERVICE_UNAVAILABLE: serviceUnavailable('Language detection service'),
  QUOTA_EXCEEDED: quotaExceeded('language detection service'),
  RATE_LIMIT_EXCEEDED: SHARED_SERVICE_ERRORS.RATE_LIMIT_EXCEEDED,
  MODEL_UNAVAILABLE: modelUnavailable('Language detection model'),
} as const;
