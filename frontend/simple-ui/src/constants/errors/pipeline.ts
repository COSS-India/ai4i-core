// Service error codes and user-facing messages

import { MAX_RECORDING_DURATION } from "../limits";

/** Speech-to-Speech Pipeline error codes and user-facing messages */
export const PIPELINE_ERRORS = {
  // Audio Recording Errors (Source Speech)
  MIC_ACCESS_DENIED: {
    title: 'Microphone access denied',
    description: 'Microphone access is required. Please allow microphone permissions in your browser settings.',
    action: 'Grant microphone permission',
  },
  MIC_NOT_FOUND: {
    title: 'Microphone not detected',
    description: 'No microphone detected. Please connect a microphone and try again.',
    action: 'Connect microphone device',
  },
  REC_START_FAILED: {
    title: 'Recording failed to start',
    description: 'Unable to start recording. Please check your microphone connection and try again.',
    action: 'Check device and retry',
  },
  REC_TOO_SHORT: {
    title: 'Recording duration too short',
    description: 'Recording must be at least 1 second for speech-to-speech translation.',
    action: 'Record longer audio',
  },
  REC_TOO_LONG: {
    title: 'Recording duration exceeds limit',
    description: `Recording exceeds maximum duration of ${MAX_RECORDING_DURATION} seconds. Please record a shorter audio clip.`,
    action: 'Record shorter audio',
  },
  REC_INTERRUPTED: {
    title: 'Recording interrupted',
    description: 'Recording was interrupted. Please try recording again.',
    action: 'Restart recording',
  },
  NO_SPEECH_DETECTED: {
    title: 'No speech detected',
    description: 'No speech detected in the recording. Please speak clearly and try again.',
    action: 'Record with clear speech',
  },
  POOR_AUDIO_QUALITY: {
    title: 'Audio quality insufficient',
    description: 'Audio quality is too low. Please record in a quieter environment.',
    action: 'Record in quiet space',
  },
  // Audio Upload Errors (Source Speech) - reuse UPLOAD_ERRORS codes
  // Pipeline Processing Errors
  ASR_FAILED: {
    title: 'ASR processing failed',
    description: 'Speech recognition failed. Please try with clearer audio.',
    action: 'Upload better quality audio',
  },
  TRANSLATION_FAILED: {
    title: 'Translation failed',
    description: 'Translation failed during processing. Please try again.',
    action: 'Retry',
  },
  TTS_FAILED: {
    title: 'TTS generation failed',
    description: 'Speech generation failed. Please try again.',
    action: 'Retry',
  },
  PIPELINE_TIMEOUT: {
    title: 'Pipeline timeout',
    description: 'Speech-to-speech translation timed out. Please try with shorter audio.',
    action: 'Upload shorter audio',
  },
  S2S_LANGUAGE_PAIR_NOT_SUPPORTED: {
    title: 'Language pair not supported',
    description: 'Speech-to-speech translation from {source} to {target} is not supported.',
    action: 'Select supported pair',
  },
  SERVICE_UNAVAILABLE: {
    title: 'Service unavailable',
    description: 'Speech-to-speech service is temporarily unavailable. Please try again later.',
    action: 'Retry after some time',
  },
  QUOTA_EXCEEDED: {
    title: 'Quota exceeded',
    description: 'You have exceeded your usage quota. Please contact your administrator.',
    action: 'Contact admin or wait',
  },
  RATE_LIMIT_EXCEEDED: {
    title: 'Rate limit exceeded',
    description: 'Too many requests. Please wait before trying again.',
    action: 'Wait and retry',
  },
  MODEL_UNAVAILABLE: {
    title: 'Model unavailable',
    description: 'One or more required models are unavailable. Please try again later.',
    action: 'Retry later',
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
  // Output Errors
  PLAYBACK_FAILED: {
    title: 'Audio playback failed',
    description: 'Unable to play translated audio. Please try regenerating or download the file.',
    action: 'Regenerate or download',
  },
  DOWNLOAD_FAILED: {
    title: 'Download failed',
    description: 'Failed to download translated audio. Please try again.',
    action: 'Retry download',
  },
} as const;
