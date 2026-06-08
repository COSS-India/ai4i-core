// Service error codes and user-facing messages

import { MAX_RECORDING_DURATION } from "../limits";

/** Audio upload error codes and user-facing messages */
export const UPLOAD_ERRORS = {
  NO_FILE_SELECTED: {
    title: 'No file selected',
    description: 'Please select an audio file to upload.',
    action: 'Select a file',
  },
  UNSUPPORTED_FORMAT: {
    title: 'File format not supported',
    description: 'File format not supported. Please upload audio files in WAV, or MP3 format.',
    action: 'Convert file format',
  },
  FILE_TOO_LARGE: {
    title: 'File size exceeds limit',
    description: 'File size exceeds maximum limit. Please upload a smaller file.',
    action: 'Compress or trim file',
  },
  INVALID_FILE: {
    title: 'File corrupted or invalid',
    description: 'The uploaded file appears to be corrupted or invalid. Please try a different file.',
    action: 'Upload different file',
  },
  UPLOAD_FAILED: {
    title: 'Upload failed',
    description: 'File upload failed. Please check your internet connection and try again.',
    action: 'Retry upload',
  },
  AUDIO_TOO_SHORT: {
    title: 'File duration too short',
    description: 'Audio file must be at least 1 second long. Please upload a longer audio file.',
    action: 'Upload longer file',
  },
  AUDIO_TOO_LONG: {
    title: 'File duration exceeds limit',
    description: `Audio file exceeds maximum duration of ${MAX_RECORDING_DURATION} seconds. Please upload a shorter file.`,
    action: 'Upload shorter file',
  },
  EMPTY_AUDIO_FILE: {
    title: 'Empty audio file',
    description: 'Unable to detect audio in this file. Please upload a file with audible content.',
    action: 'Upload valid file',
  },
  UPLOAD_TIMEOUT: {
    title: 'Upload timeout',
    description: 'Upload timed out. Please check your internet connection and try again.',
    action: 'Check connection and retry',
  },
} as const;
