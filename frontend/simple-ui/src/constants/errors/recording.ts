// Service error codes and user-facing messages

import { MAX_RECORDING_DURATION } from "../limits";

/** Recording error codes and user-facing messages */
export const RECORDING_ERRORS = {
  REC_START_FAILED: {
    title: 'Recording failed to start',
    description: 'Unable to start recording. Please check your microphone connection and try again.',
    action: 'Check device and retry',
  },
  REC_TOO_SHORT: {
    title: 'Recording duration too short',
    description: 'Recording must be at least 1 second. Please record a longer audio clip.',
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
  BROWSER_NOT_SUPPORTED: {
    title: 'Browser not supported',
    description: 'Audio recording is not supported in your browser. Please use Chrome, Firefox, or Safari.',
    action: 'Switch browser',
  },
  NO_AUDIO_DETECTED: {
    title: 'No audio detected',
    description: "No speech detected in the recording. Please ensure you're speaking clearly and try again.",
    action: 'Record with clear speech',
  },
} as const;
