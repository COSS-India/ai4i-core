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

export const SPEAKER_DIARIZATION_ERRORS = {
  // Recording Errors (handled by useAudioRecorder, but included for completeness)
  MIC_PERMISSION_DENIED: SHARED_MIC_ERRORS.MIC_PERMISSION_DENIED,
  MIC_NOT_FOUND: SHARED_MIC_ERRORS.MIC_NOT_FOUND,
  RECORDING_FAILED: RECORDING_ERRORS.REC_START_FAILED,
  RECORDING_TOO_SHORT: {
    title: 'Recording duration too short',
    description: 'Please provide sufficient audio for speaker diarization.',
    action: 'Record longer audio',
  },
  RECORDING_TOO_LONG: RECORDING_ERRORS.REC_TOO_LONG,
  // Upload Errors (handled by AudioRecorder component, but included for completeness)
  FILE_REQUIRED: UPLOAD_ERRORS.NO_FILE_SELECTED,
  INVALID_FORMAT: SHARED_AUDIO_UPLOAD_ERRORS.INVALID_FORMAT,
  FILE_TOO_LARGE: SHARED_AUDIO_UPLOAD_ERRORS.FILE_TOO_LARGE,
  INVALID_FILE: UPLOAD_ERRORS.INVALID_FILE,
  UPLOAD_FAILED: UPLOAD_ERRORS.UPLOAD_FAILED,
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
  EMPTY_AUDIO: UPLOAD_ERRORS.EMPTY_AUDIO_FILE,
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
  SERVICE_UNAVAILABLE: serviceUnavailable('Speaker diarization service'),
  PROCESSING_TIMEOUT: {
    title: 'Processing timeout',
    description: 'Audio processing timed out. Please try with a shorter audio file.',
    action: 'Upload shorter file',
  },
  QUOTA_EXCEEDED: quotaExceeded('speaker diarization service'),
  RATE_LIMIT_EXCEEDED: SHARED_SERVICE_ERRORS.RATE_LIMIT_EXCEEDED,
  MODEL_UNAVAILABLE: modelUnavailable('Speaker diarization model'),
} as const;
