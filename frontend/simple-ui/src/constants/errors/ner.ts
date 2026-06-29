// Service error codes and user-facing messages

import { MAX_TEXT_LENGTH } from "../limits";
import {
  SHARED_SERVICE_ERRORS,
  quotaExceeded,
  serviceUnavailable,
} from "../errorShared";

export const NER_ERRORS = {
  // Input Errors
  TEXT_REQUIRED: {
    title: 'No text provided',
    description: 'Please enter text for entity recognition.',
    action: 'Enter text',
  },
  TEXT_TOO_SHORT: {
    title: 'Text too short',
    description: 'This text is too short for entity recognition. Please provide more text.',
    action: 'Enter longer text',
  },
  TEXT_TOO_LONG: {
    title: 'Text exceeds limit',
    description: `This text is too long to process. Please reduce the text length (max ${MAX_TEXT_LENGTH} characters).`,
    action: 'Reduce text length',
  },
  INVALID_CHARACTERS: {
    title: 'Invalid characters',
    description: 'Text contains invalid characters. Please remove special symbols and try again.',
    action: 'Remove invalid characters',
  },
  // Processing Errors
  LANGUAGE_MISMATCH: {
    title: 'Language mismatch',
    description: 'Text language doesn\'t match the selected language. Please enter text in the selected language.',
    action: 'Enter matching text',
  },
  NO_ENTITIES_FOUND: {
    title: 'No entities found',
    description: 'No entities detected in the provided text. Please verify your input text.',
    action: 'Verify input text',
  },
  SERVICE_UNAVAILABLE: serviceUnavailable('Named entity recognition service'),
  PROCESSING_FAILED: {
    title: 'Processing failed',
    description: 'Entity recognition failed. Please try again.',
    action: 'Retry',
  },
  QUOTA_EXCEEDED: quotaExceeded('NER service'),
  RATE_LIMIT_EXCEEDED: SHARED_SERVICE_ERRORS.RATE_LIMIT_EXCEEDED,
  MODEL_UNAVAILABLE: {
    title: 'Model unavailable',
    description: 'The selected NER model is currently unavailable. Please try a different model.',
    action: 'Select different model',
  },
  INVALID_REQUEST: SHARED_SERVICE_ERRORS.INVALID_REQUEST,
  // Authentication & Authorization Errors
  AUTHENTICATION_REQUIRED: {
    title: 'Authentication required',
    description: 'Authentication is required to access this service. Please log in.',
    action: 'Log in',
  },
  INVALID_CREDENTIALS: {
    title: 'Invalid credentials',
    description: 'Invalid credentials provided. Please log in again.',
    action: 'Re-authenticate',
  },
  ACCOUNT_LOCKED: {
    title: 'Account locked',
    description: 'Your account has been locked. Please contact support for assistance.',
    action: 'Contact support',
  },
  ACCOUNT_SUSPENDED: {
    title: 'Account suspended',
    description: 'Your account has been suspended. Please contact your administrator.',
    action: 'Contact admin',
  },
  MAX_LOGIN_ATTEMPTS: {
    title: 'Max login attempts',
    description: 'Too many failed login attempts. Please try again later or reset your password.',
    action: 'Try later or reset password',
  },
} as const;
