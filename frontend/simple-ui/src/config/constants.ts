// Configuration constants for Simple UI

import {
  NETWORK_ERROR_ENTRY,
  SHARED_AUDIO_UPLOAD_ERRORS,
  SHARED_MIC_ERRORS,
  SHARED_SERVICE_ERRORS,
  modelUnavailable,
  quotaExceeded,
  serviceUnavailable,
} from './errorShared';

export { UI_ERROR_MESSAGES, PARSE_ERROR_MESSAGES } from './errorShared';

// Supported languages with script codes
export const SUPPORTED_LANGUAGES = [
  { code: "en", label: "English", scriptCode: "Latn" },
  { code: "hi", label: "Hindi", scriptCode: "Deva" },
  { code: "ta", label: "Tamil", scriptCode: "Taml" },
  { code: "te", label: "Telugu", scriptCode: "Telu" },
  { code: "kn", label: "Kannada", scriptCode: "Knda" },
  { code: "ml", label: "Malayalam", scriptCode: "Mlym" },
  { code: "bn", label: "Bengali", scriptCode: "Beng" },
  { code: "gu", label: "Gujarati", scriptCode: "Gujr" },
  { code: "mr", label: "Marathi", scriptCode: "Deva" },
  { code: "pa", label: "Punjabi", scriptCode: "Guru" },
  { code: "or", label: "Oriya", scriptCode: "Orya" },
  { code: "as", label: "Assamese", scriptCode: "Beng" },
  { code: "ur", label: "Urdu", scriptCode: "Arab" },
  { code: "sa", label: "Sanskrit", scriptCode: "Deva" },
  { code: "ks", label: "Kashmiri", scriptCode: "Arab" },
  { code: "ne", label: "Nepali", scriptCode: "Deva" },
  { code: "sd", label: "Sindhi", scriptCode: "Arab" },
  { code: "kok", label: "Konkani", scriptCode: "Deva" },
  { code: "doi", label: "Dogri", scriptCode: "Deva" },
  { code: "mai", label: "Maithili", scriptCode: "Deva" },
  { code: "brx", label: "Bodo", scriptCode: "Deva" },
  { code: "mni", label: "Manipuri", scriptCode: "Beng" },
  { code: "gom", label: "Goan Konkani", scriptCode: "Latn" },
  { code: "sat", label: "Santali", scriptCode: "Latn" },
  // Custom additions
  // African languages
  { code: "sw", label: "Swahili", scriptCode: "Latn" },
  { code: "yo", label: "Yoruba", scriptCode: "Latn" },
  { code: "ha", label: "Hausa", scriptCode: "Latn" },
  { code: "so", label: "Somali", scriptCode: "Latn" },
  { code: "am", label: "Amharic", scriptCode: "Ethi" },
  { code: "ti", label: "Tigrinya", scriptCode: "Ethi" },
  { code: "ig", label: "Igbo", scriptCode: "Latn" },
  { code: "zu", label: "Zulu", scriptCode: "Latn" },
  { code: "xh", label: "Xhosa", scriptCode: "Latn" },
  { code: "sn", label: "Shona", scriptCode: "Latn" },
  { code: "rw", label: "Kinyarwanda", scriptCode: "Latn" },
  { code: "om", label: "Oromo", scriptCode: "Latn" },
  { code: "lg", label: "Ganda", scriptCode: "Latn" },
  { code: "wo", label: "Wolof", scriptCode: "Latn" },
  { code: "ts", label: "Tsonga", scriptCode: "Latn" },
  { code: "tn", label: "Tswana", scriptCode: "Latn" },
  { code: "af", label: "Afrikaans", scriptCode: "Latn" },
  { code: "fr", label: "French", scriptCode: "Latn" },
  { code: "ar", label: "Arabic", scriptCode: "Arab" },
];

//LLM-supported languages (matching LLM service supported languages)
export const LLM_SUPPORTED_LANGUAGES = [
  { code: "en", label: "English", scriptCode: "Latn" },
  { code: "hi", label: "Hindi", scriptCode: "Deva" },
  { code: "ta", label: "Tamil", scriptCode: "Taml" },
  { code: "te", label: "Telugu", scriptCode: "Telu" },
  { code: "kn", label: "Kannada", scriptCode: "Knda" },
  { code: "ml", label: "Malayalam", scriptCode: "Mlym" },
  { code: "bn", label: "Bengali", scriptCode: "Beng" },
  { code: "gu", label: "Gujarati", scriptCode: "Gujr" },
  { code: "mr", label: "Marathi", scriptCode: "Deva" },
  { code: "pa", label: "Punjabi", scriptCode: "Guru" },
  { code: "or", label: "Oriya", scriptCode: "Orya" },
  { code: "as", label: "Assamese", scriptCode: "Beng" },
  { code: "ur", label: "Urdu", scriptCode: "Arab" },
  { code: "sa", label: "Sanskrit", scriptCode: "Deva" },
  { code: "ks", label: "Kashmiri", scriptCode: "Arab" },
  { code: "ne", label: "Nepali", scriptCode: "Deva" },
  { code: "sd", label: "Sindhi", scriptCode: "Arab" },
  { code: "kok", label: "Konkani", scriptCode: "Deva" },
  { code: "doi", label: "Dogri", scriptCode: "Deva" },
  { code: "mai", label: "Maithili", scriptCode: "Deva" },
  { code: "brx", label: "Bodo", scriptCode: "Deva" },
  { code: "mni", label: "Manipuri", scriptCode: "Beng" },
  { code: "gom", label: "Goan Konkani", scriptCode: "Latn" },
  { code: "sat", label: "Santali", scriptCode: "Latn" },
];

// ASR-supported languages (matching ASR service supported languages)
export const ASR_SUPPORTED_LANGUAGES = [
  { code: "as", label: "Assamese", scriptCode: "Beng" },
  { code: "bn", label: "Bengali", scriptCode: "Beng" },
  { code: "brx", label: "Bodo", scriptCode: "Deva" },
  { code: "doi", label: "Dogri", scriptCode: "Deva" },
  { code: "gu", label: "Gujarati", scriptCode: "Gujr" },
  { code: "hi", label: "Hindi", scriptCode: "Deva" },
  { code: "kn", label: "Kannada", scriptCode: "Knda" },
  { code: "ks", label: "Kashmiri", scriptCode: "Arab" },
  { code: "mai", label: "Maithili", scriptCode: "Deva" },
  { code: "ml", label: "Malayalam", scriptCode: "Mlym" },
  { code: "mni", label: "Manipuri", scriptCode: "Beng" },
  { code: "mr", label: "Marathi", scriptCode: "Deva" },
  { code: "ne", label: "Nepali", scriptCode: "Deva" },
  { code: "or", label: "Odia", scriptCode: "Orya" },
  { code: "pa", label: "Punjabi", scriptCode: "Guru" },
  { code: "sa", label: "Sanskrit", scriptCode: "Deva" },
  { code: "sd", label: "Sindhi", scriptCode: "Arab" },
  { code: "ta", label: "Tamil", scriptCode: "Taml" },
  { code: "te", label: "Telugu", scriptCode: "Telu" },
  { code: "ur", label: "Urdu", scriptCode: "Arab" },
];

// TTS-supported languages (matching TTS service supported languages)
export const TTS_SUPPORTED_LANGUAGES = [
  { code: "hi", label: "Hindi", scriptCode: "Deva" },
  { code: "mr", label: "Marathi", scriptCode: "Deva" },
  { code: "as", label: "Assamese", scriptCode: "Beng" },
  { code: "bn", label: "Bengali", scriptCode: "Beng" },
  { code: "gu", label: "Gujarati", scriptCode: "Gujr" },
  { code: "or", label: "Odia", scriptCode: "Orya" },
  { code: "pa", label: "Punjabi", scriptCode: "Guru" },
];

// Language code to label mapping
export const LANG_CODE_TO_LABEL: { [key: string]: string } =
  SUPPORTED_LANGUAGES.reduce((acc, lang) => {
    acc[lang.code] = lang.label;
    return acc;
  }, {} as { [key: string]: string });

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

// Maximum text length
export const MAX_TEXT_LENGTH = 512;

/** Guest users may make this many inference requests per service per hour. */
export const GUEST_REQUESTS_PER_HOUR_PER_SERVICE = 10;

/**
 * AI4IDS-2584 / AI4IDS-2688: Home Page + Navigation show only the LLM model task type.
 * Set to `false` to restore the full NLP/Pipeline catalog in Home/Nav.
 */
export const LLM_ONLY_HOME_AND_NAV = true;

/** Sidebar section label (was "Services"). */
export const MODEL_TASK_TYPE_NAV_LABEL = "Model task type";

/** Client-side anonymous try-it request limit (matches tryItService). */
export const ANONYMOUS_TRY_IT_REQUESTS_PER_HOUR = 5;

// Minimum recording duration in seconds
export const MIN_RECORDING_DURATION = 1;

// Maximum recording duration in seconds
export const MAX_RECORDING_DURATION = 60;

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

// Maximum file size for audio uploads (10MB)
export const MAX_AUDIO_FILE_SIZE = 10 * 1024 * 1024; // 10MB

// Maximum file size for image uploads (10MB)
export const MAX_IMAGE_FILE_SIZE = 10 * 1024 * 1024; // 10MB

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

/** ASR service error codes and user-facing messages */
export const ASR_ERRORS = {
  LANGUAGE_NOT_SUPPORTED: {
    title: 'Language not supported',
    description: 'Uploaded audio language doesn\'t match selected language. Upload audio in selected language.',
    action: 'Select supported language',
  },
  SERVICE_UNAVAILABLE: serviceUnavailable('ASR service'),
  PROCESSING_TIMEOUT: {
    title: 'Processing timeout',
    description: 'Audio processing timed out. Please try with a shorter audio file or try again later.',
    action: 'Upload shorter file or retry',
  },
  QUOTA_EXCEEDED: quotaExceeded('ASR service', ' or try again tomorrow'),
  MODEL_UNAVAILABLE: {
    title: 'Model not available',
    description: 'The selected ASR model is currently unavailable. Please try a different model or contact support.',
    action: 'Select different model',
  },
  RATE_LIMIT_EXCEEDED: SHARED_SERVICE_ERRORS.RATE_LIMIT_EXCEEDED,
  POOR_AUDIO_QUALITY: {
    title: 'Poor audio quality',
    description: 'Audio quality is too poor for accurate transcription. Please provide clearer audio.',
    action: 'Upload better quality audio',
  },
  INVALID_REQUEST: SHARED_SERVICE_ERRORS.INVALID_REQUEST,
  AUTH_FAILED: SHARED_SERVICE_ERRORS.AUTH_FAILED,
  TENANT_SUSPENDED: SHARED_SERVICE_ERRORS.TENANT_SUSPENDED,
} as const;

/** Minimum TTS text length (characters) to be considered valid */
export const MIN_TTS_TEXT_LENGTH = 2;

/** TTS (Text-to-Speech) error codes and user-facing messages */
export const TTS_ERRORS = {
  // Input errors
  NO_TEXT_INPUT: {
    title: 'No text provided',
    description: 'Please enter text to convert to speech.',
    action: 'Enter text',
  },
  TEXT_TOO_SHORT: {
    title: 'Text too short',
    description: 'Please provide sufficient text to convert.',
    action: 'Enter longer text',
  },
  TEXT_TOO_LONG: {
    title: 'Text exceeds limit',
    description: 'Text exceeds maximum limit. Please reduce the text length.',
    action: 'Reduce text length',
  },
  INVALID_CHARACTERS: {
    title: 'Invalid characters',
    description: 'Text contains invalid characters. Please use only alphanumeric characters and punctuation.',
    action: 'Remove invalid characters',
  },
  EMPTY_INPUT: {
    title: 'Empty input',
    description: 'Text input cannot be empty. Please enter some text.',
    action: 'Enter text',
  },
  LANGUAGE_MISMATCH: {
    title: 'Language mismatch',
    description: "The text language doesn't match the selected language. Please select the correct language.",
    action: 'Select correct language',
  },
  // Service processing errors
  LANGUAGE_NOT_SUPPORTED: {
    title: 'Language not supported',
    description: 'The selected language is not supported for TTS. Please choose from: Hindi, English, Tamil, Telugu, Bengali.',
    action: 'Select supported language',
  },
  VOICE_NOT_AVAILABLE: {
    title: 'Voice not available',
    description: 'The selected voice is not available for this language. Please choose a different voice.',
    action: 'Select different voice',
  },
  SERVICE_UNAVAILABLE: serviceUnavailable('TTS service'),
  PROCESSING_FAILED: {
    title: 'Processing failed',
    description: 'Failed to generate speech. Please try again.',
    action: 'Retry',
  },
  QUOTA_EXCEEDED: quotaExceeded('TTS service', ' or try again tomorrow'),
  RATE_LIMIT_EXCEEDED: SHARED_SERVICE_ERRORS.RATE_LIMIT_EXCEEDED,
  MODEL_UNAVAILABLE: {
    title: 'Model not available',
    description: 'The selected TTS model is currently unavailable. Please try a different model.',
    action: 'Select different model',
  },
  AUDIO_GEN_FAILED: {
    title: 'Audio generation failed',
    description: 'Audio generation failed. Please try again or contact support if the issue persists.',
    action: 'Retry or contact support',
  },
  INVALID_REQUEST: SHARED_SERVICE_ERRORS.INVALID_REQUEST,
  AUTH_FAILED: SHARED_SERVICE_ERRORS.AUTH_FAILED,
  TENANT_SUSPENDED: SHARED_SERVICE_ERRORS.TENANT_SUSPENDED,
  // Output errors
  PLAYBACK_FAILED: {
    title: 'Audio playback failed',
    description: 'Unable to play generated audio. Please try regenerating or download the file.',
    action: 'Regenerate or download',
  },
  DOWNLOAD_FAILED: {
    title: 'Download failed',
    description: 'Failed to download audio file. Please try again.',
    action: 'Retry download',
  },
  AUDIO_FORMAT_ERROR: {
    title: 'Audio format error',
    description: 'Generated audio format is not supported by your browser. Please try downloading instead.',
    action: 'Download file',
  },
} as const;

/** Minimum NMT text length (characters) to be considered valid */
export const MIN_NMT_TEXT_LENGTH = 2;

/** NMT (Neural Machine Translation) error codes and user-facing messages */
export const NMT_ERRORS = {
  // Input errors
  NO_TEXT_INPUT: {
    title: 'No text provided',
    description: 'Please enter text to translate.',
    action: 'Enter text',
  },
  TEXT_TOO_SHORT: {
    title: 'Text too short',
    description: 'Please provide sufficient text to translate.',
    action: 'Enter longer text',
  },
  TEXT_TOO_LONG: {
    title: 'Text exceeds limit',
    description: 'Text exceeds maximum limit. Please reduce the text length.',
    action: 'Reduce text length',
  },
  INVALID_CHARACTERS: {
    title: 'Invalid characters',
    description: 'Text contains unsupported characters. Please remove special symbols and try again.',
    action: 'Remove invalid characters',
  },
  EMPTY_INPUT: {
    title: 'Empty input',
    description: 'Text input cannot be empty. Please enter some text.',
    action: 'Enter text',
  },
  SAME_LANGUAGE_ERROR: {
    title: 'Source and target same',
    description: 'Source and target languages cannot be the same. Please select different languages.',
    action: 'Change language selection',
  },
  // Service processing errors
  LANGUAGE_PAIR_NOT_SUPPORTED: {
    title: 'Language pair not supported',
    description: 'Translation from {source} to {target} is not supported. Please check available language pairs.',
    action: 'Select supported pair',
  },
  SERVICE_UNAVAILABLE: serviceUnavailable('Translation service'),
  TRANSLATION_FAILED: {
    title: 'Translation failed',
    description: 'Translation failed. Please try again.',
    action: 'Retry',
  },
  QUOTA_EXCEEDED: quotaExceeded('translation service'),
  RATE_LIMIT_EXCEEDED: SHARED_SERVICE_ERRORS.RATE_LIMIT_EXCEEDED,
  MODEL_UNAVAILABLE: {
    title: 'Model not available',
    description: 'The selected translation model is currently unavailable. Please try a different model.',
    action: 'Select different model',
  },
  INVALID_REQUEST: SHARED_SERVICE_ERRORS.INVALID_REQUEST,
  AUTH_FAILED: SHARED_SERVICE_ERRORS.AUTH_FAILED,
  TENANT_SUSPENDED: SHARED_SERVICE_ERRORS.TENANT_SUSPENDED,
} as const;

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
  SERVICE_UNAVAILABLE: serviceUnavailable('Transliteration'),
  PROCESSING_FAILED: {
    title: 'Processing failed',
    description: 'Transliteration failed. Please try again.',
    action: 'Retry',
  },
  QUOTA_EXCEEDED: quotaExceeded('transliteration'),
  RATE_LIMIT_EXCEEDED: SHARED_SERVICE_ERRORS.RATE_LIMIT_EXCEEDED,
  MODEL_UNAVAILABLE: {
    title: 'Model unavailable',
    description: 'The selected transliteration model is currently unavailable. Please try another model.',
    action: 'Select different model',
  },
} as const;

/** Minimum Language Detection text length (characters) to be considered valid */
export const MIN_LANGUAGE_DETECTION_TEXT_LENGTH = 2;

/** Maximum total input length for Text Language Detection textarea */
export const MAX_LANGUAGE_DETECTION_INPUT_LENGTH = 512;

/** Language Detection error codes and user-facing messages */
export const LANGUAGE_DETECTION_ERRORS = {
  // Input Errors
  TEXT_REQUIRED: {
    title: 'No text provided',
    description: 'Please enter text to detect language.',
    action: 'Enter text',
  },
  TEXT_TOO_SHORT: {
    title: 'Text too short',
    description: 'Please provide sufficient text to detect language.',
    action: 'Enter longer text',
  },
  TEXT_TOO_LONG: {
    title: 'Text exceeds limit',
    description: `Text input is too long. Please reduce the text length.`,
    action: 'Reduce text length',
  },
  // Processing Errors
  DETECTION_FAILED: {
    title: 'Detection failed',
    description: 'Cannot detect language from the provided text. Please try with longer or more distinctive text.',
    action: 'Enter longer text',
  },
  SERVICE_UNAVAILABLE: serviceUnavailable('Language detection service'),
  QUOTA_EXCEEDED: quotaExceeded('language detection service'),
  RATE_LIMIT_EXCEEDED: SHARED_SERVICE_ERRORS.RATE_LIMIT_EXCEEDED,
  MODEL_UNAVAILABLE: modelUnavailable('Language detection model'),
} as const;

/** Speaker Diarization error codes and user-facing messages */
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

/** Audio Language Detection error codes and user-facing messages */
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

/** Minimum NER text length (characters) to be considered valid */
export const MIN_NER_TEXT_LENGTH = 2;

/** Named Entity Recognition (NER) error codes and user-facing messages */
export const NER_ERRORS = {
  // Input Errors
  TEXT_REQUIRED: {
    title: 'No text provided',
    description: 'Please enter text for entity recognition.',
    action: 'Enter text',
  },
  TEXT_TOO_SHORT: {
    title: 'Text too short',
    description: 'This text is too short for entity recognition. Please provide more text.',
    action: 'Enter longer text',
  },
  TEXT_TOO_LONG: {
    title: 'Text exceeds limit',
    description: `This text is too long to process. Please reduce the text length (max ${MAX_TEXT_LENGTH} characters).`,
    action: 'Reduce text length',
  },
  INVALID_CHARACTERS: {
    title: 'Invalid characters',
    description: 'Text contains invalid characters. Please remove special symbols and try again.',
    action: 'Remove invalid characters',
  },
  // Processing Errors
  LANGUAGE_MISMATCH: {
    title: 'Language mismatch',
    description: 'Text language doesn\'t match the selected language. Please enter text in the selected language.',
    action: 'Enter matching text',
  },
  NO_ENTITIES_FOUND: {
    title: 'No entities found',
    description: 'No entities detected in the provided text. Please verify your input text.',
    action: 'Verify input text',
  },
  SERVICE_UNAVAILABLE: serviceUnavailable('Named entity recognition service'),
  PROCESSING_FAILED: {
    title: 'Processing failed',
    description: 'Entity recognition failed. Please try again.',
    action: 'Retry',
  },
  QUOTA_EXCEEDED: quotaExceeded('NER service'),
  RATE_LIMIT_EXCEEDED: SHARED_SERVICE_ERRORS.RATE_LIMIT_EXCEEDED,
  MODEL_UNAVAILABLE: {
    title: 'Model unavailable',
    description: 'The selected NER model is currently unavailable. Please try a different model.',
    action: 'Select different model',
  },
  INVALID_REQUEST: SHARED_SERVICE_ERRORS.INVALID_REQUEST,
  // Authentication & Authorization Errors
  AUTHENTICATION_REQUIRED: {
    title: 'Authentication required',
    description: 'Authentication is required to access this service. Please log in.',
    action: 'Log in',
  },
  INVALID_CREDENTIALS: {
    title: 'Invalid credentials',
    description: 'Invalid credentials provided. Please log in again.',
    action: 'Re-authenticate',
  },
  ACCOUNT_LOCKED: {
    title: 'Account locked',
    description: 'Your account has been locked. Please contact support for assistance.',
    action: 'Contact support',
  },
  ACCOUNT_SUSPENDED: {
    title: 'Account suspended',
    description: 'Your account has been suspended. Please contact your administrator.',
    action: 'Contact admin',
  },
  MAX_LOGIN_ATTEMPTS: {
    title: 'Max login attempts',
    description: 'Too many failed login attempts. Please try again later or reset your password.',
    action: 'Try later or reset password',
  },
} as const;

/** Speech-to-Speech Pipeline error codes and user-facing messages */
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

/** Common Network and System Errors (All Services) */
export const COMMON_ERRORS = {
  NETWORK_ERROR: NETWORK_ERROR_ENTRY,
  INTERNAL_SERVER_ERROR: {
    title: 'Server error',
    description: 'An internal server error occurred. Please try again later or contact support.',
    action: 'Retry or contact support',
  },
  GATEWAY_TIMEOUT: {
    title: 'Gateway timeout',
    description: 'Request timed out. Please try again.',
    action: 'Retry',
  },
  SERVICE_MAINTENANCE: {
    title: 'Service maintenance',
    description: 'Service is under maintenance. Please try again after some time.',
    action: 'Wait and retry',
  },
  INVALID_RESPONSE: {
    title: 'Invalid API response',
    description: 'Received invalid response from server. Please try again.',
    action: 'Retry',
  },
  SESSION_EXPIRED: {
    title: 'Session expired',
    description: 'Your session has expired. Please log in again.',
    action: 'Re-authenticate',
  },
  UNAUTHORIZED: {
    title: 'Unauthorized access',
    description: 'You don\'t have permission to access this service. Please contact your administrator.',
    action: 'Contact admin',
  },
  INVALID_TENANT: {
    title: 'Invalid tenant',
    description: 'Invalid tenant configuration. Please contact support.',
    action: 'Contact support',
  },
  NOT_FOUND: {
    title: 'Resource not found',
    description: 'Requested resource not found. Please verify and try again.',
    action: 'Verify input',
  },
} as const;

/** OCR (Optical Character Recognition) error codes and user-facing messages */
export const OCR_ERRORS = {
  // Upload Errors
  FILE_REQUIRED: {
    title: 'No file selected',
    description: 'Please select an image file to upload.',
    action: 'Select a file',
  },
  INVALID_FORMAT: {
    title: 'File format not supported',
    description: 'File format not supported. Please upload files in JPG or PNG format.',
    action: 'Convert file format',
  },
  FILE_TOO_LARGE: UPLOAD_ERRORS.FILE_TOO_LARGE,
  INVALID_FILE: UPLOAD_ERRORS.INVALID_FILE,
  UPLOAD_FAILED: UPLOAD_ERRORS.UPLOAD_FAILED,
  EMPTY_FILE: {
    title: 'Empty file',
    description: 'The uploaded file contains no data. Please upload a valid file.',
    action: 'Upload valid file',
  },
  IMAGE_RESOLUTION_LOW: {
    title: 'Image resolution low',
    description: 'Image resolution is too low for accurate text extraction. Please use a higher quality image.',
    action: 'Upload better quality image',
  },
  // Processing Errors
  LANGUAGE_MISMATCH: {
    title: 'Language mismatch',
    description: 'Image text doesn\'t match the selected language. Please upload an image in the selected language.',
    action: 'Upload matching image',
  },
  NO_TEXT_DETECTED: {
    title: 'No text detected',
    description: 'No text detected in the image. Please ensure the image contains readable text.',
    action: 'Upload image with text',
  },
  TEXT_TOO_BLURRY: {
    title: 'Text too blurry',
    description: 'Text is too blurry to read accurately. Please use a clearer image.',
    action: 'Upload clearer image',
  },
  SERVICE_UNAVAILABLE: serviceUnavailable('OCR service'),
  PROCESSING_TIMEOUT: {
    title: 'Processing timeout',
    description: 'Image processing timed out. Please try with a smaller file.',
    action: 'Upload smaller file',
  },
  QUOTA_EXCEEDED: quotaExceeded('OCR service'),
  RATE_LIMIT_EXCEEDED: SHARED_SERVICE_ERRORS.RATE_LIMIT_EXCEEDED,
  MODEL_UNAVAILABLE: {
    title: 'Model unavailable',
    description: 'The selected OCR model is currently unavailable. Please try a different model.',
    action: 'Select different model',
  },
  INVALID_REQUEST: SHARED_SERVICE_ERRORS.INVALID_REQUEST,
} as const;

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

// API endpoints (canonical definitions live in services/apiEndpoints.ts)
export { apiEndpoints as API_ENDPOINTS } from "../services/apiEndpoints";

// WebSocket events
export const WEBSOCKET_EVENTS = {
  CONNECT: "connect",
  DISCONNECT: "disconnect",
  START: "start",
  DATA: "data",
  RESPONSE: "response",
  ERROR: "error",
} as const;

/** Sidebar nav item ids (kebab-case segments; `home` uses path `/` not `/home`). */
export const TABS = {
  home: "home",
  modelManagement: "model-management",
  servicesManagement: "services-management",
  tenantManagement: "tenant-management",
  apiKeyManagement: "api-key-management",
  logs: "logs",
  usageDashboard: "usage-dashboard",
  traces: "traces",
  alertsManagement: "alerts-management",
  piiManagement: "pii-management",
  tierManagement: "tier-management",
  policyManagement: "policy-management",
  nmt: "nmt",
  asr: "asr",
  tts: "tts",
  llm: "llm",
  pipeline: "pipeline",
  ocr: "ocr",
  transliteration: "transliteration",
  languageDetection: "language-detection",
  speakerDiarization: "speaker-diarization",
  languageDiarization: "language-diarization",
  audioLanguageDetection: "audio-language-detection",
  ner: "ner",
} as const;

/** Tenant lifecycle and user statuses (auth-service). Canonical values are UPPERCASE. */
export const TENANT = {
  STATUS: {
    PENDING: "PENDING",
    ACTIVE: "ACTIVE",
    SUSPENDED: "SUSPENDED",
    DEACTIVATED: "DEACTIVATED",
  },
  USER_STATUS: {
    PENDING: "PENDING",
    ACTIVE: "ACTIVE",
    /** UI-only: user has not completed setup / password (is_active=false, not tenant-suspended). */
    PENDING_ACTIVATION: "PENDING_ACTIVATION",
    SUSPENDED: "SUSPENDED",
  },
} as const;

export type TenantStatusValue = (typeof TENANT.STATUS)[keyof typeof TENANT.STATUS];
export type TenantUserStatusValue = (typeof TENANT.USER_STATUS)[keyof typeof TENANT.USER_STATUS];

/** All tenant lifecycle statuses (static; used for filters and labels). */
export const TENANT_STATUS_LIST: readonly TenantStatusValue[] = [
  TENANT.STATUS.PENDING,
  TENANT.STATUS.ACTIVE,
  TENANT.STATUS.SUSPENDED,
  TENANT.STATUS.DEACTIVATED,
];

/** Statuses an admin may set via PATCH (excludes PENDING). */
export const TENANT_ADMIN_UPDATABLE_STATUSES: readonly TenantStatusValue[] = [
  TENANT.STATUS.ACTIVE,
  TENANT.STATUS.SUSPENDED,
  TENANT.STATUS.DEACTIVATED,
];

/** Allowed PATCH transitions — keep in sync with auth-service tenant_lifecycle.py. */
export const ALLOWED_TENANT_STATUS_TRANSITIONS: Readonly<
  Record<TenantStatusValue, readonly TenantStatusValue[]>
> = {
  [TENANT.STATUS.PENDING]: [TENANT.STATUS.DEACTIVATED],
  [TENANT.STATUS.ACTIVE]: [TENANT.STATUS.SUSPENDED, TENANT.STATUS.DEACTIVATED],
  [TENANT.STATUS.SUSPENDED]: [TENANT.STATUS.ACTIVE, TENANT.STATUS.DEACTIVATED],
  [TENANT.STATUS.DEACTIVATED]: [TENANT.STATUS.ACTIVE],
};

/** Tenant-user lifecycle statuses for filters and badges (not tenant PENDING/DEACTIVATED). */
export const TENANT_USER_STATUS_LIST: readonly TenantUserStatusValue[] = [
  TENANT.USER_STATUS.PENDING,
  TENANT.USER_STATUS.ACTIVE,
  TENANT.USER_STATUS.PENDING_ACTIVATION,
  TENANT.USER_STATUS.SUSPENDED,
];

/** Minimal fields needed to derive tenant-user display status. */
export type TenantUserStatusSource = {
  is_active: boolean;
  is_tenant_active?: boolean | null;
  /** True once the user completed setup (set a password). */
  is_activated?: boolean | null;
};

/** True when tenant lifecycle status blocks all users at the tenant level. */
export function isTenantLifecycleBlockingUsers(
  tenantStatus?: string | null
): boolean {
  return (
    isTenantStatus(tenantStatus, TENANT.STATUS.SUSPENDED) ||
    isTenantStatus(tenantStatus, TENANT.STATUS.DEACTIVATED)
  );
}

/**
 * Derive tenant-user display status for UI badges and action menus.
 *
 * A user who never completed setup (no credentials → ``is_activated`` falsy and
 * ``is_active`` false) is always Pending Activation, even while the tenant is
 * SUSPENDED/DEACTIVATED. Suspended implies a previously active account was
 * blocked, which is semantically wrong for an unactivated user; treating them
 * as Suspended could also strand them if the tenant is reactivated. When the
 * tenant blocks users, only previously active/activated users show Suspended.
 */
export function resolveTenantUserDisplayStatus(
  user: TenantUserStatusSource,
  tenantStatus?: string | null
): TenantUserStatusValue {
  // Never completed setup → Pending Activation, regardless of tenant lifecycle
  // or a stale ``is_tenant_active`` left over from the old lock-everyone cascade.
  if (!user.is_active && !user.is_activated) {
    return TENANT.USER_STATUS.PENDING_ACTIVATION;
  }

  // Tenant lifecycle cascade: previously active/activated users show Suspended.
  if (isTenantLifecycleBlockingUsers(tenantStatus)) {
    return TENANT.USER_STATUS.SUSPENDED;
  }

  if (user.is_active && (user.is_tenant_active ?? true)) {
    return TENANT.USER_STATUS.ACTIVE;
  }
  // Inactive with credentials → admin-suspended (per-user Suspend) or locked by
  // the tenant lifecycle cascade (``is_tenant_active`` false).
  return TENANT.USER_STATUS.SUSPENDED;
}

/** Status to apply when toggling Suspend/Activate on a tenant user. */
export function getTenantUserStatusToggleTarget(
  user: TenantUserStatusSource
): TenantUserStatusValue {
  const display = resolveTenantUserDisplayStatus(user);
  return display === TENANT.USER_STATUS.ACTIVE
    ? TENANT.USER_STATUS.SUSPENDED
    : TENANT.USER_STATUS.ACTIVE;
}

/** Suspend/Activate action label for tenant users (Delete is a separate action). */
export function getTenantUserStatusActionLabel(user: TenantUserStatusSource): string {
  const display = resolveTenantUserDisplayStatus(user);
  if (display === TENANT.USER_STATUS.ACTIVE) return "Suspend";
  if (display === TENANT.USER_STATUS.SUSPENDED) return "Activate";
  // Not used in the new Pending actions menu, but keep a sensible default.
  return "Activate";
}

const TENANT_STATUS_LABELS: Record<TenantStatusValue, string> = {
  [TENANT.STATUS.PENDING]: "Pending Activation",
  [TENANT.STATUS.ACTIVE]: "Active",
  [TENANT.STATUS.SUSPENDED]: "Suspended",
  [TENANT.STATUS.DEACTIVATED]: "Deactivated",
};

const TENANT_USER_STATUS_LABELS: Record<TenantUserStatusValue, string> = {
  [TENANT.USER_STATUS.PENDING]: "Pending",
  [TENANT.USER_STATUS.ACTIVE]: "Active",
  [TENANT.USER_STATUS.PENDING_ACTIVATION]: "Pending Activation",
  [TENANT.USER_STATUS.SUSPENDED]: "Suspended",
};

export function normalizeTenantStatus(status: string): TenantStatusValue {
  return status.trim().toUpperCase() as TenantStatusValue;
}

/** Title-case label for tenant lifecycle status (UI only). */
export function formatTenantStatusLabel(status: string | null | undefined): string {
  if (!status?.trim()) return "—";
  const normalized = normalizeTenantStatus(status);
  return TENANT_STATUS_LABELS[normalized] ?? status;
}

/** Title-case label for tenant user status (UI only). */
export function formatTenantUserStatusLabel(status: string | null | undefined): string {
  if (!status?.trim()) return "—";
  const upper = status.trim().toUpperCase();
  if (upper in TENANT_USER_STATUS_LABELS) {
    return TENANT_USER_STATUS_LABELS[upper as TenantUserStatusValue];
  }
  return status;
}

export function isTenantStatus(
  actual: string | null | undefined,
  expected: TenantStatusValue
): boolean {
  return normalizeTenantStatus(actual ?? "") === expected;
}

export function isTenantUserStatus(
  actual: string | null | undefined,
  expected: TenantUserStatusValue
): boolean {
  return (actual ?? "").trim().toUpperCase() === expected;
}

/** Chakra colorScheme for tenant / tenant-user status badges. */
export function getTenantStatusColorScheme(status?: string | null): string {
  if (isTenantStatus(status, TENANT.STATUS.ACTIVE)) return "green";
  if (isTenantStatus(status, TENANT.STATUS.SUSPENDED)) return "orange";
  if (isTenantStatus(status, TENANT.STATUS.DEACTIVATED)) return "red";
  if (isTenantStatus(status, TENANT.STATUS.PENDING)) return "blue";
  if (isTenantUserStatus(status, TENANT.USER_STATUS.PENDING_ACTIVATION)) return "blue";
  if (isTenantUserStatus(status, TENANT.USER_STATUS.SUSPENDED)) return "orange";
  if (isTenantUserStatus(status, TENANT.USER_STATUS.PENDING)) return "gray";
  return "gray";
}

/** Target statuses offered as row actions for the given tenant status. */
export function getTenantStatusActionTargets(
  currentStatus: string | null | undefined,
  options?: { onboardingCompleted?: boolean }
): TenantStatusValue[] {
  const current = normalizeTenantStatus(currentStatus ?? "");
  const targets = [...(ALLOWED_TENANT_STATUS_TRANSITIONS[current] ?? [])];
  // PENDING → Deactivate is a soft delete: never-verified tenants have no
  // status actions (no Activate). ACTIVE → Deactivate keeps Activate.
  if (
    current === TENANT.STATUS.DEACTIVATED &&
    options?.onboardingCompleted === false
  ) {
    return targets.filter((status) => status !== TENANT.STATUS.ACTIVE);
  }
  return targets;
}

/** Action button label when changing tenant status. */
export function getTenantStatusActionLabel(
  targetStatus: TenantStatusValue,
  currentStatus?: string | null
): string {
  const current = currentStatus ? normalizeTenantStatus(currentStatus) : null;
  if (
    targetStatus === TENANT.STATUS.ACTIVE &&
    current === TENANT.STATUS.DEACTIVATED
  ) {
    return "Reactivate";
  }
  switch (targetStatus) {
    case TENANT.STATUS.ACTIVE:
      return "Activate";
    case TENANT.STATUS.SUSPENDED:
      return "Suspend";
    case TENANT.STATUS.DEACTIVATED:
      return "Deactivate";
    default:
      return formatTenantStatusLabel(targetStatus);
  }
}

/** API key list filter + effective display status (aligns with auth-service effective_is_active). */
export const API_KEY = {
  FILTER_STATUS: {
    ALL: "all",
    ACTIVE: "active",
    INACTIVE: "inactive",
    REVOKED: "revoked",
  },
  DISPLAY_STATUS: {
    ACTIVE: "active",
    INACTIVE: "inactive",
    REVOKED: "revoked",
  },
} as const;

export type ApiKeyFilterStatusValue =
  (typeof API_KEY.FILTER_STATUS)[keyof typeof API_KEY.FILTER_STATUS];

export type ApiKeyDisplayStatusValue =
  (typeof API_KEY.DISPLAY_STATUS)[keyof typeof API_KEY.DISPLAY_STATUS];

export const API_KEY_FILTER_STATUS_LIST: readonly Exclude<
  ApiKeyFilterStatusValue,
  typeof API_KEY.FILTER_STATUS.ALL
>[] = [
  API_KEY.FILTER_STATUS.ACTIVE,
  API_KEY.FILTER_STATUS.INACTIVE,
  API_KEY.FILTER_STATUS.REVOKED,
];

const API_KEY_STATUS_LABELS: Record<ApiKeyDisplayStatusValue, string> = {
  [API_KEY.DISPLAY_STATUS.ACTIVE]: "Active",
  [API_KEY.DISPLAY_STATUS.INACTIVE]: "Inactive",
  [API_KEY.DISPLAY_STATUS.REVOKED]: "Revoked",
};

/** Owner + tenant context for deriving effective API key status in the UI. */
export type ApiKeyAccessContext = {
  userIsActive?: boolean;
  userTenantActive?: boolean | null;
  tenantStatus?: string | null;
};

export type ApiKeyStatusSource = {
  is_active?: boolean;
  is_revoked?: boolean;
  expires_at?: string | null;
};

export function isApiKeyExpired(expiresAt?: string | null): boolean {
  if (!expiresAt) return false;
  try {
    return new Date(expiresAt).getTime() < Date.now();
  } catch {
    return false;
  }
}

/** Mirrors auth-service APIKeyService.user_may_use_api_keys (frontend-only). */
export function userMayUseApiKeys(context: ApiKeyAccessContext): boolean {
  if (context.userIsActive === false) return false;
  if (context.userTenantActive === false) return false;
  if (isTenantLifecycleBlockingUsers(context.tenantStatus)) return false;
  return true;
}

/**
 * Effective API key status for UI badges/filters.
 * Revoked: DB flag or tenant deactivated. Inactive: suspended/locked/expired.
 */
export function resolveApiKeyDisplayStatus(
  key: ApiKeyStatusSource,
  context: ApiKeyAccessContext = {}
): ApiKeyDisplayStatusValue {
  if (key.is_active === false || key.is_revoked === true) {
    return API_KEY.DISPLAY_STATUS.REVOKED;
  }
  if (isTenantStatus(context.tenantStatus, TENANT.STATUS.DEACTIVATED)) {
    return API_KEY.DISPLAY_STATUS.REVOKED;
  }
  if (isApiKeyExpired(key.expires_at)) {
    return API_KEY.DISPLAY_STATUS.INACTIVE;
  }
  if (!userMayUseApiKeys(context)) {
    return API_KEY.DISPLAY_STATUS.INACTIVE;
  }
  return API_KEY.DISPLAY_STATUS.ACTIVE;
}

export function isApiKeyEffectivelyActive(
  key: ApiKeyStatusSource,
  context: ApiKeyAccessContext = {}
): boolean {
  return resolveApiKeyDisplayStatus(key, context) === API_KEY.DISPLAY_STATUS.ACTIVE;
}

/** Human-readable reason when status is Inactive (empty for Active/Revoked). */
export function getApiKeyInactiveReason(context: ApiKeyAccessContext): string {
  if (context.userIsActive === false) {
    return "Your account is inactive.";
  }
  if (context.userTenantActive === false) {
    return "Tenant access is suspended for your account.";
  }
  if (isTenantStatus(context.tenantStatus, TENANT.STATUS.SUSPENDED)) {
    return "Tenant is suspended — API keys are temporarily inactive and will resume automatically when the tenant is reactivated.";
  }
  return "API key access is currently blocked.";
}

/** Human-readable reason when status is Revoked due to tenant deactivation. */
export function getApiKeyRevokedReason(context: ApiKeyAccessContext): string | null {
  if (isTenantStatus(context.tenantStatus, TENANT.STATUS.DEACTIVATED)) {
    return "Tenant was deactivated — this API key is revoked. Create a new key after the tenant is reactivated.";
  }
  return null;
}

export function getApiKeyDisplayStatusColorScheme(
  status: ApiKeyDisplayStatusValue
): string {
  switch (status) {
    case API_KEY.DISPLAY_STATUS.ACTIVE:
      return "green";
    case API_KEY.DISPLAY_STATUS.INACTIVE:
      return "orange";
    case API_KEY.DISPLAY_STATUS.REVOKED:
      return "red";
    default:
      return "gray";
  }
}

export function formatApiKeyDisplayStatusLabel(
  status: ApiKeyDisplayStatusValue
): string {
  return API_KEY_STATUS_LABELS[status] ?? status;
}

export function formatApiKeyFilterStatusLabel(status: string): string {
  const key = status.trim().toLowerCase() as ApiKeyDisplayStatusValue;
  return API_KEY_STATUS_LABELS[key] ?? status;
}

export function formatApiKeyActiveLabel(isActive: boolean): string {
  return isActive
    ? API_KEY_STATUS_LABELS[API_KEY.DISPLAY_STATUS.ACTIVE]
    : API_KEY_STATUS_LABELS[API_KEY.DISPLAY_STATUS.REVOKED];
}

export function isApiKeyFilterStatus(
  actual: string,
  expected: Exclude<ApiKeyFilterStatusValue, typeof API_KEY.FILTER_STATUS.ALL>
): boolean {
  return actual.trim().toLowerCase() === expected;
}

/** Model version lifecycle (model-management). */
export const MODEL_VERSION = {
  STATUS: {
    ACTIVE: "ACTIVE",
    DEPRECATED: "DEPRECATED",
  },
  FILTER: {
    ALL: "",
    ACTIVE: "active",
    DEPRECATED: "deprecated",
  },
} as const;

export const MODEL_VERSION_FILTER_LIST: readonly (typeof MODEL_VERSION.FILTER)[keyof typeof MODEL_VERSION.FILTER][] =
  [MODEL_VERSION.FILTER.ACTIVE, MODEL_VERSION.FILTER.DEPRECATED];

export function isModelVersionStatusActive(status?: string | null): boolean {
  const normalized = (status ?? MODEL_VERSION.STATUS.ACTIVE).trim().toUpperCase();
  return normalized === MODEL_VERSION.STATUS.ACTIVE || normalized === "";
}

export function isModelVersionFilterStatus(
  actual: string,
  expected: (typeof MODEL_VERSION.FILTER)[keyof typeof MODEL_VERSION.FILTER]
): boolean {
  return actual.trim().toLowerCase() === expected;
}

export function formatModelVersionStatusLabel(status?: string | null): string {
  return isModelVersionStatusActive(status) ? "Active" : "Deprecated";
}

export function isModelVersionStatusDeprecated(status?: string | null): boolean {
  if (!status?.trim()) return false;
  return status.trim().toUpperCase() === MODEL_VERSION.STATUS.DEPRECATED;
}

export function formatModelVersionFilterLabel(filter: string): string {
  if (isModelVersionFilterStatus(filter, MODEL_VERSION.FILTER.ACTIVE)) return "Active";
  if (isModelVersionFilterStatus(filter, MODEL_VERSION.FILTER.DEPRECATED)) return "Deprecated";
  return filter;
}

/**
 * Inference task types (platform TaskTypeEnum).
 * Static list for model/service registry task-type filters.
 */
export const MODEL_TASK_TYPE_LIST = [
  "asr",
  "nmt",
  "tts",
  "llm",
  "transliteration",
  "language-detection",
  "speaker-diarization",
  "audio-lang-detection",
  "language-diarization",
  "ocr",
  "ner",
] as const;

export type ModelTaskTypeValue = (typeof MODEL_TASK_TYPE_LIST)[number];

/** Display label for task-type filter options (matches table badges). */
export function formatModelTaskTypeLabel(taskType: string): string {
  return taskType.trim().toUpperCase();
}

/** Sentinel returned by GET for inferenceApiKey.value — never echo back on PATCH. */
export const MODEL_API_KEY_REDACTED = "[REDACTED]";

/** ULCA field length limits (AI4IDS-2478) — used for client-side create validation. */
export const MODEL_FIELD_LIMITS = {
  NAME_MIN: 5,
  NAME_MAX: 100,
  VERSION_MIN: 1,
  VERSION_MAX: 20,
  DESCRIPTION_MIN: 25,
  DESCRIPTION_MAX: 1000,
  REF_URL_MIN: 5,
  REF_URL_MAX: 200,
  LICENSE_URL_MAX: 500,
  SUBMITTER_NAME_MIN: 3,
  SUBMITTER_NAME_MAX: 50,
  TEAM_NAME_MIN: 5,
  TEAM_NAME_MAX: 50,
} as const;

/** Service publish state (services-management). */
export const SERVICE_PUBLISH = {
  FILTER: {
    ALL: "",
    PUBLISHED: "published",
    UNPUBLISHED: "unpublished",
  },
  LABEL: {
    PUBLISHED: "Published",
    UNPUBLISHED: "Unpublished",
  },
} as const;

export const SERVICE_PUBLISH_FILTER_LIST: readonly (typeof SERVICE_PUBLISH.FILTER)["PUBLISHED" | "UNPUBLISHED"][] =
  [SERVICE_PUBLISH.FILTER.PUBLISHED, SERVICE_PUBLISH.FILTER.UNPUBLISHED];

export function isServicePublishFilterStatus(
  actual: string,
  expected: (typeof SERVICE_PUBLISH.FILTER)["PUBLISHED"] | (typeof SERVICE_PUBLISH.FILTER)["UNPUBLISHED"]
): boolean {
  return actual.trim().toLowerCase() === expected;
}

export function formatServicePublishLabel(isPublished: boolean): string {
  return isPublished ? SERVICE_PUBLISH.LABEL.PUBLISHED : SERVICE_PUBLISH.LABEL.UNPUBLISHED;
}

export function formatServicePublishFilterLabel(filter: string): string {
  if (isServicePublishFilterStatus(filter, SERVICE_PUBLISH.FILTER.PUBLISHED)) {
    return SERVICE_PUBLISH.LABEL.PUBLISHED;
  }
  if (isServicePublishFilterStatus(filter, SERVICE_PUBLISH.FILTER.UNPUBLISHED)) {
    return SERVICE_PUBLISH.LABEL.UNPUBLISHED;
  }
  return filter;
}

export { METERING } from "./meteringConstants";
export type { MeteringHeatmapServiceKey } from "./meteringConstants";

/** Password policy — keep in sync with auth-service PASSWORD_MIN/MAX_LENGTH. */
export const PASSWORD_POLICY = {
  MIN_LENGTH: 8,
  MAX_LENGTH: 64,
} as const;

/** Set-password token validation statuses (auth-service). */
export const SET_PASSWORD_TOKEN = {
  STATUS: {
    VALID: "valid",
    EXPIRED: "expired",
    INVALID: "invalid",
    USED: "used",
  },
} as const;

export type SetPasswordTokenStatusValue =
  (typeof SET_PASSWORD_TOKEN.STATUS)[keyof typeof SET_PASSWORD_TOKEN.STATUS];

export function isSetPasswordTokenStatus(
  actual: string,
  expected: SetPasswordTokenStatusValue
): boolean {
  return actual.trim().toLowerCase() === expected;
}
