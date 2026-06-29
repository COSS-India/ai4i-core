// Service error codes and user-facing messages

import { MAX_RECORDING_DURATION } from "../limits";
import {
  SHARED_MIC_ERRORS,
  SHARED_SERVICE_ERRORS,
  quotaExceeded,
  serviceUnavailable,
} from "../errorShared";
import { RECORDING_ERRORS } from "./recording";

export const PIPELINE_ERRORS = {
  // Audio Recording Errors (Source Speech)
  MIC_ACCESS_DENIED: SHARED_MIC_ERRORS.MIC_PERMISSION_DENIED,
  MIC_NOT_FOUND: SHARED_MIC_ERRORS.MIC_NOT_FOUND,
  REC_START_FAILED: RECORDING_ERRORS.REC_START_FAILED,
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
  REC_INTERRUPTED: RECORDING_ERRORS.REC_INTERRUPTED,
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
  SERVICE_UNAVAILABLE: serviceUnavailable('Speech-to-speech service', 'later'),
  QUOTA_EXCEEDED: quotaExceeded('this service'),
  RATE_LIMIT_EXCEEDED: SHARED_SERVICE_ERRORS.RATE_LIMIT_EXCEEDED,
  MODEL_UNAVAILABLE: {
    title: 'Model unavailable',
    description: 'One or more required models are unavailable. Please try again later.',
    action: 'Retry later',
  },
  AUTH_FAILED: SHARED_SERVICE_ERRORS.AUTH_FAILED,
  TENANT_SUSPENDED: SHARED_SERVICE_ERRORS.TENANT_SUSPENDED,
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
