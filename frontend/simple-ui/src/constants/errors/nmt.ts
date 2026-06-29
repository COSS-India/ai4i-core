// Service error codes and user-facing messages

import {
  SHARED_SERVICE_ERRORS,
  quotaExceeded,
  serviceUnavailable,
} from "../errorShared";

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
  SERVICE_UNAVAILABLE: serviceUnavailable('Translation service'),
  TRANSLATION_FAILED: {
    title: 'Translation failed',
    description: 'Translation failed. Please try again.',
    action: 'Retry',
  },
  QUOTA_EXCEEDED: quotaExceeded('translation service'),
  RATE_LIMIT_EXCEEDED: SHARED_SERVICE_ERRORS.RATE_LIMIT_EXCEEDED,
  MODEL_UNAVAILABLE: {
    title: 'Model not available',
    description: 'The selected translation model is currently unavailable. Please try a different model.',
    action: 'Select different model',
  },
  INVALID_REQUEST: SHARED_SERVICE_ERRORS.INVALID_REQUEST,
  AUTH_FAILED: SHARED_SERVICE_ERRORS.AUTH_FAILED,
  TENANT_SUSPENDED: SHARED_SERVICE_ERRORS.TENANT_SUSPENDED,
} as const;
