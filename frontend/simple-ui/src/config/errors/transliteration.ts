// Service error codes and user-facing messages

import { MAX_TEXT_LENGTH } from "../limits";

/** Minimum Transliteration text length (characters) to be considered valid */
export const MIN_TRANSLITERATION_TEXT_LENGTH = 2;

/** Transliteration error codes and user-facing messages */
export const TRANSLITERATION_ERRORS = {
  // Input Errors
  TEXT_REQUIRED: {
    title: 'No text provided',
    description: 'Please enter text to transliterate.',
    action: 'Enter text',
  },
  TEXT_TOO_SHORT: {
    title: 'Text too short',
    description: 'Please provide sufficient text to transliterate.',
    action: 'Enter longer text',
  },
  TEXT_TOO_LONG: {
    title: 'Text exceeds limit',
    description: `Text exceeds maximum limit of ${MAX_TEXT_LENGTH} characters. Please reduce the text length.`,
    action: 'Reduce text length',
  },
  INVALID_CHARACTERS: {
    title: 'Invalid characters',
    description: 'Text contains invalid characters for the selected script.',
    action: 'Remove invalid characters',
  },
  // Processing Errors
  LANGUAGE_PAIR_NOT_SUPPORTED: {
    title: 'Language pair not supported',
    description: 'Transliteration from selected source to target script is not supported. Please check available options.',
    action: 'Select supported pair',
  },
  SCRIPT_MISMATCH: {
    title: 'Script mismatch',
    description: 'Input script doesn\'t match the selected source language. Please verify your input.',
    action: 'Verify input script',
  },
  SERVICE_UNAVAILABLE: {
    title: 'Service unavailable',
    description: 'Transliteration is temporarily unavailable. Please try again in a few minutes.',
    action: 'Retry after some time',
  },
  PROCESSING_FAILED: {
    title: 'Processing failed',
    description: 'Transliteration failed. Please try again.',
    action: 'Retry',
  },
  QUOTA_EXCEEDED: {
    title: 'Quota exceeded',
    description: 'You have exceeded your usage quota for transliteration. Please contact your administrator.',
    action: 'Contact admin or wait',
  },
  RATE_LIMIT_EXCEEDED: {
    title: 'Rate limit exceeded',
    description: 'Too many requests. Please wait before trying again.',
    action: 'Wait and retry',
  },
  MODEL_UNAVAILABLE: {
    title: 'Model unavailable',
    description: 'The selected transliteration model is currently unavailable. Please try another model.',
    action: 'Select different model',
  },
} as const;
