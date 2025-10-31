// Configuration constants for Simple UI

// Supported languages with script codes
export const SUPPORTED_LANGUAGES = [
  { code: 'en', label: 'English', scriptCode: 'Latn' },
  { code: 'hi', label: 'Hindi', scriptCode: 'Deva' },
  { code: 'ta', label: 'Tamil', scriptCode: 'Taml' },
  { code: 'te', label: 'Telugu', scriptCode: 'Telu' },
  { code: 'kn', label: 'Kannada', scriptCode: 'Knda' },
  { code: 'ml', label: 'Malayalam', scriptCode: 'Mlym' },
  { code: 'bn', label: 'Bengali', scriptCode: 'Beng' },
  { code: 'gu', label: 'Gujarati', scriptCode: 'Gujr' },
  { code: 'mr', label: 'Marathi', scriptCode: 'Deva' },
  { code: 'pa', label: 'Punjabi', scriptCode: 'Guru' },
  { code: 'or', label: 'Oriya', scriptCode: 'Orya' },
  { code: 'as', label: 'Assamese', scriptCode: 'Beng' },
  { code: 'ur', label: 'Urdu', scriptCode: 'Arab' },
  { code: 'sa', label: 'Sanskrit', scriptCode: 'Deva' },
  { code: 'ks', label: 'Kashmiri', scriptCode: 'Arab' },
  { code: 'ne', label: 'Nepali', scriptCode: 'Deva' },
  { code: 'sd', label: 'Sindhi', scriptCode: 'Arab' },
  { code: 'kok', label: 'Konkani', scriptCode: 'Deva' },
  { code: 'doi', label: 'Dogri', scriptCode: 'Deva' },
  { code: 'mai', label: 'Maithili', scriptCode: 'Deva' },
  { code: 'brx', label: 'Bodo', scriptCode: 'Deva' },
  { code: 'mni', label: 'Manipuri', scriptCode: 'Beng' },
  { code: 'gom', label: 'Goan Konkani', scriptCode: 'Latn' },
  { code: 'sat', label: 'Santali', scriptCode: 'Latn' },
  // African languages
  { code: 'sw', label: 'Swahili', scriptCode: 'Latn' },
  { code: 'yo', label: 'Yoruba', scriptCode: 'Latn' },
  { code: 'ha', label: 'Hausa', scriptCode: 'Latn' },
  { code: 'so', label: 'Somali', scriptCode: 'Latn' },
  { code: 'am', label: 'Amharic', scriptCode: 'Ethi' },
  { code: 'ti', label: 'Tigrinya', scriptCode: 'Ethi' },
  { code: 'ig', label: 'Igbo', scriptCode: 'Latn' },
  { code: 'zu', label: 'Zulu', scriptCode: 'Latn' },
  { code: 'xh', label: 'Xhosa', scriptCode: 'Latn' },
  { code: 'sn', label: 'Shona', scriptCode: 'Latn' },
  { code: 'rw', label: 'Kinyarwanda', scriptCode: 'Latn' },
  { code: 'om', label: 'Oromo', scriptCode: 'Latn' },
  { code: 'lg', label: 'Ganda', scriptCode: 'Latn' },
  { code: 'wo', label: 'Wolof', scriptCode: 'Latn' },
  { code: 'ts', label: 'Tsonga', scriptCode: 'Latn' },
  { code: 'tn', label: 'Tswana', scriptCode: 'Latn' },
  { code: 'af', label: 'Afrikaans', scriptCode: 'Latn' },
  { code: 'fr', label: 'French', scriptCode: 'Latn' },
  { code: 'ar', label: 'Arabic', scriptCode: 'Arab' },
];

// Language code to label mapping
export const LANG_CODE_TO_LABEL: { [key: string]: string } = SUPPORTED_LANGUAGES.reduce(
  (acc, lang) => {
    acc[lang.code] = lang.label;
    return acc;
  },
  {} as { [key: string]: string }
);

// Audio formats
export const AUDIO_FORMATS = ['wav', 'mp3', 'flac', 'ogg', 'pcm'] as const;

// Sample rates for ASR
export const ASR_SAMPLE_RATES = [8000, 16000, 48000] as const;

// Sample rates for TTS
export const TTS_SAMPLE_RATES = [8000, 16000, 22050, 44100, 48000] as const;

// Gender options for TTS
export const GENDER_OPTIONS = [
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
] as const;

// Maximum text length
export const MAX_TEXT_LENGTH = 512;

// Maximum recording duration in seconds
export const MAX_RECORDING_DURATION = 120;

// Utility function to format duration in seconds to MM:SS format
export const formatDuration = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
};

// Default configurations
export const DEFAULT_ASR_CONFIG = {
  language: 'en',
  sampleRate: 16000,
  audioFormat: 'wav',
  encoding: 'base64',
} as const;

export const DEFAULT_TTS_CONFIG = {
  language: 'en',
  gender: 'female',
  sampleRate: 22050,
  audioFormat: 'wav',
} as const;

export const DEFAULT_NMT_CONFIG = {
  sourceLanguage: 'en',
  targetLanguage: 'hi',
} as const;

// API endpoints
export const API_ENDPOINTS = {
  asr: {
    inference: '/api/v1/asr/inference',
    models: '/api/v1/asr/models',
    health: '/api/v1/asr/health',
  },
  tts: {
    inference: '/api/v1/tts/inference',
    voices: '/api/v1/tts/voices',
    health: '/api/v1/tts/health',
  },
  nmt: {
    inference: '/api/v1/nmt/inference',
    models: '/api/v1/nmt/models',
    languages: '/api/v1/nmt/languages',
    health: '/api/v1/nmt/health',
  },
  pipeline: {
    inference: '/api/v1/pipeline/inference',
    info: '/api/v1/pipeline/info',
    health: '/api/v1/pipeline/health',
  },
} as const;

// WebSocket events
export const WEBSOCKET_EVENTS = {
  CONNECT: 'connect',
  DISCONNECT: 'disconnect',
  START: 'start',
  DATA: 'data',
  RESPONSE: 'response',
  ERROR: 'error',
} as const;