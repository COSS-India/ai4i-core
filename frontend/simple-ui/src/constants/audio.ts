// Audio formats, sample rates, and default service configs

// Audio formats
export const AUDIO_FORMATS = ["wav", "mp3"] as const;

// Sample rates for ASR
export const ASR_SAMPLE_RATES = [8000, 16000, 48000] as const;

// Sample rates for TTS
export const TTS_SAMPLE_RATES = [22050] as const;

// Gender options for TTS
export const GENDER_OPTIONS = [
  { value: "male", label: "Male" },
  { value: "female", label: "Female" },
] as const;

// Utility function to format duration in seconds to MM:SS format
export const formatDuration = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, "0")}:${secs
    .toString()
    .padStart(2, "0")}`;
};

// Default configurations
export const DEFAULT_ASR_CONFIG = {
  language: "", // User must select; no default to avoid implicit preference
  sampleRate: 16000,
  serviceId: "", // User must select; no default to avoid implicit preference
  audioFormat: "wav",
  encoding: "base64",
} as const;

export const DEFAULT_TTS_CONFIG = {
  language: "", // User must select; no default to avoid implicit preference
  gender: "",
  sampleRate: 22050,
  audioFormat: "", // User must select; no default to avoid implicit preference
} as const;

export const DEFAULT_NMT_CONFIG = {
  sourceLanguage: "", // User must select; no default to avoid implicit preference
  targetLanguage: "",
  sourceScriptCode: "",
  targetScriptCode: "",
} as const;
