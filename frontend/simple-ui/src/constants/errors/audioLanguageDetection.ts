// Service error codes and user-facing messages

import { MAX_RECORDING_DURATION } from "../limits";
import {
  SHARED_AUDIO_UPLOAD_ERRORS,
  SHARED_MIC_ERRORS,
  SHARED_SERVICE_ERRORS,
  modelUnavailable,
  quotaExceeded,
  serviceUnavailable,
} from "../errorShared";
import { RECORDING_ERRORS } from "./recording";
import { UPLOAD_ERRORS } from "./upload";

export const AUDIO_LANGUAGE_DETECTION_ERRORS = {
  // Recording Errors (handled by useAudioRecorder, but included for completeness)
  MIC_PERMISSION_DENIED: SHARED_MIC_ERRORS.MIC_PERMISSION_DENIED,
  MIC_NOT_FOUND: SHARED_MIC_ERRORS.MIC_NOT_FOUND,
  RECORDING_FAILED: RECORDING_ERRORS.REC_START_FAILED,
  RECORDING_TOO_SHORT: {
    title: 'Recording duration too short',
    description: 'This recording is too short for language detection. Please record a longer audio clip.',
    action: 'Record longer audio',
  },
  RECORDING_TOO_LONG: {
    title: 'Recording duration exceeds limit',
    description: `This recording is too long to process. Please record a shorter audio clip (max ${MAX_RECORDING_DURATION} seconds).`,
    action: 'Record shorter audio',
  },
  // Upload Errors (handled by AudioRecorder component, but included for completeness)
  FILE_REQUIRED: UPLOAD_ERRORS.NO_FILE_SELECTED,
  INVALID_FORMAT: SHARED_AUDIO_UPLOAD_ERRORS.INVALID_FORMAT,
  FILE_TOO_LARGE: SHARED_AUDIO_UPLOAD_ERRORS.FILE_TOO_LARGE,
  INVALID_FILE: UPLOAD_ERRORS.INVALID_FILE,
  UPLOAD_FAILED: UPLOAD_ERRORS.UPLOAD_FAILED,
  AUDIO_TOO_SHORT: {
    title: 'File duration too short',
    description: 'This audio file is too short for language detection. Please upload a longer recording.',
    action: 'Upload longer file',
  },
  AUDIO_TOO_LONG: {
    title: 'File duration exceeds limit',
    description: `This audio file is too long to process. Please upload a shorter recording (max ${MAX_RECORDING_DURATION} seconds).`,
    action: 'Upload shorter file',
  },
  EMPTY_AUDIO: UPLOAD_ERRORS.EMPTY_AUDIO_FILE,
  // Processing Errors
  NO_SPEECH_DETECTED: {
    title: 'No speech detected',
    description: 'No speech detected in the audio. Please use audio with clear speech.',
    action: 'Upload audio with speech',
  },
  DETECTION_FAILED: {
    title: 'Detection failed',
    description: 'Cannot detect language from the audio. Please use clearer audio with more speech.',
    action: 'Upload clearer audio',
  },
  CONFIDENCE_TOO_LOW: {
    title: 'Confidence too low',
    description: 'Detection confidence is too low. Please use longer audio with clearer speech.',
    action: 'Upload longer audio',
  },
  AUDIO_QUALITY_POOR: {
    title: 'Audio quality poor',
    description: 'Audio quality is too low for accurate language detection. Please provide clearer audio.',
    action: 'Upload better quality audio',
  },
  SERVICE_UNAVAILABLE: serviceUnavailable('Audio language detection service'),
  PROCESSING_TIMEOUT: {
    title: 'Processing timeout',
    description: 'Audio processing timed out. Please try with a shorter audio file.',
    action: 'Upload shorter file',
  },
  QUOTA_EXCEEDED: quotaExceeded('audio language detection service'),
  RATE_LIMIT_EXCEEDED: SHARED_SERVICE_ERRORS.RATE_LIMIT_EXCEEDED,
  MODEL_UNAVAILABLE: modelUnavailable('Audio language detection model'),
} as const;
