// Service error codes and user-facing messages

import { MAX_RECORDING_DURATION } from "../limits";

/** Speaker Diarization error codes and user-facing messages */
export const SPEAKER_DIARIZATION_ERRORS = {
  // Recording Errors (handled by useAudioRecorder, but included for completeness)
  MIC_PERMISSION_DENIED: {
    title: 'Microphone access denied',
    description: 'Microphone access is required to record audio. Please allow microphone permissions in your browser settings.',
    action: 'Grant microphone permission',
  },
  MIC_NOT_FOUND: {
    title: 'Microphone not detected',
    description: 'No microphone detected. Please connect a microphone and try again.',
    action: 'Connect microphone device',
  },
  RECORDING_FAILED: {
    title: 'Recording failed to start',
    description: 'Unable to start recording. Please check your microphone connection and try again.',
    action: 'Check device and retry',
  },
  RECORDING_TOO_SHORT: {
    title: 'Recording duration too short',
    description: 'Please provide sufficient audio for speaker diarization.',
    action: 'Record longer audio',
  },
  RECORDING_TOO_LONG: {
    title: 'Recording duration exceeds limit',
    description: `Recording exceeds maximum duration of ${MAX_RECORDING_DURATION} seconds. Please record a shorter audio clip.`,
    action: 'Record shorter audio',
  },
  // Upload Errors (handled by AudioRecorder component, but included for completeness)
  FILE_REQUIRED: {
    title: 'No file selected',
    description: 'Please select an audio file to upload.',
    action: 'Select a file',
  },
  INVALID_FORMAT: {
    title: 'File format not supported',
    description: 'File format not supported. Please upload audio files in WAV or MP3 format.',
    action: 'Convert file format',
  },
  FILE_TOO_LARGE: {
    title: 'File size exceeds limit',
    description: 'This file is too large to process. Please upload a smaller file.',
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
    description: 'This audio file is too short for speaker identification. Please upload a longer recording.',
    action: 'Upload longer file',
  },
  AUDIO_TOO_LONG: {
    title: 'File duration exceeds limit',
    description: `This audio file is too long to process. Please upload a shorter recording (max ${MAX_RECORDING_DURATION} seconds).`,
    action: 'Upload shorter file',
  },
  EMPTY_AUDIO: {
    title: 'Empty audio file',
    description: 'Unable to detect audio in this file. Please upload a file with audible content.',
    action: 'Upload valid file',
  },
  // Processing Errors
  NO_SPEAKERS_DETECTED: {
    title: 'No speakers detected',
    description: 'No speakers detected in the audio. Please use audio with clear speech from multiple speakers.',
    action: 'Upload clearer audio',
  },
  AUDIO_QUALITY_POOR: {
    title: 'Audio quality poor',
    description: 'Audio quality is too low for accurate speaker diarization. Please provide clearer audio.',
    action: 'Upload better quality audio',
  },
  SERVICE_UNAVAILABLE: {
    title: 'Service unavailable',
    description: 'Speaker diarization service is temporarily unavailable. Please try again in a few minutes.',
    action: 'Retry after some time',
  },
  PROCESSING_TIMEOUT: {
    title: 'Processing timeout',
    description: 'Audio processing timed out. Please try with a shorter audio file.',
    action: 'Upload shorter file',
  },
  QUOTA_EXCEEDED: {
    title: 'Quota exceeded',
    description: 'You have exceeded your usage quota for speaker diarization service. Please contact your administrator.',
    action: 'Contact admin or wait',
  },
  RATE_LIMIT_EXCEEDED: {
    title: 'Rate limit exceeded',
    description: 'Too many requests. Please wait before trying again.',
    action: 'Wait and retry',
  },
  MODEL_UNAVAILABLE: {
    title: 'Model unavailable',
    description: 'Speaker diarization model is currently unavailable. Please try again later.',
    action: 'Retry later',
  },
} as const;
