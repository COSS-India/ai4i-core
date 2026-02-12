// Configuration constants for Simple UI

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
  SERVICE_UNAVAILABLE: {
    title: 'Service unavailable',
    description: 'ASR service is temporarily unavailable. Please try again in a few minutes.',
    action: 'Retry after some time',
  },
  PROCESSING_TIMEOUT: {
    title: 'Processing timeout',
    description: 'Audio processing timed out. Please try with a shorter audio file or try again later.',
    action: 'Upload shorter file or retry',
  },
  QUOTA_EXCEEDED: {
    title: 'Quota exceeded',
    description: 'You have exceeded your usage quota for ASR service. Please contact your administrator or try again tomorrow.',
    action: 'Contact admin or wait',
  },
  MODEL_UNAVAILABLE: {
    title: 'Model not available',
    description: 'The selected ASR model is currently unavailable. Please try a different model or contact support.',
    action: 'Select different model',
  },
  RATE_LIMIT_EXCEEDED: {
    title: 'Rate limit exceeded',
    description: 'Too many requests. Please wait before trying again.',
    action: 'Wait and retry',
  },
  POOR_AUDIO_QUALITY: {
    title: 'Poor audio quality',
    description: 'Audio quality is too poor for accurate transcription. Please provide clearer audio.',
    action: 'Upload better quality audio',
  },
  INVALID_REQUEST: {
    title: 'Invalid request',
    description: 'Invalid request parameters. Please check your input and try again.',
    action: 'Verify input parameters',
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
  SERVICE_UNAVAILABLE: {
    title: 'Service unavailable',
    description: 'TTS service is temporarily unavailable. Please try again in a few minutes.',
    action: 'Retry after some time',
  },
  PROCESSING_FAILED: {
    title: 'Processing failed',
    description: 'Failed to generate speech. Please try again.',
    action: 'Retry',
  },
  QUOTA_EXCEEDED: {
    title: 'Quota exceeded',
    description: 'You have exceeded your usage quota for TTS service. Please contact your administrator or try again tomorrow.',
    action: 'Contact admin or wait',
  },
  RATE_LIMIT_EXCEEDED: {
    title: 'Rate limit exceeded',
    description: 'Too many requests. Please wait before trying again.',
    action: 'Wait and retry',
  },
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
  INVALID_REQUEST: {
    title: 'Invalid request',
    description: 'Invalid request parameters. Please check your input and try again.',
    action: 'Verify input parameters',
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
  SERVICE_UNAVAILABLE: {
    title: 'Service unavailable',
    description: 'Translation service is temporarily unavailable. Please try again in a few minutes.',
    action: 'Retry after some time',
  },
  TRANSLATION_FAILED: {
    title: 'Translation failed',
    description: 'Translation failed. Please try again.',
    action: 'Retry',
  },
  QUOTA_EXCEEDED: {
    title: 'Quota exceeded',
    description: 'You have exceeded your usage quota for translation service. Please contact your administrator.',
    action: 'Contact admin or wait',
  },
  RATE_LIMIT_EXCEEDED: {
    title: 'Rate limit exceeded',
    description: 'Too many requests. Please wait before trying again.',
    action: 'Wait and retry',
  },
  MODEL_UNAVAILABLE: {
    title: 'Model not available',
    description: 'The selected translation model is currently unavailable. Please try a different model.',
    action: 'Select different model',
  },
  INVALID_REQUEST: {
    title: 'Invalid request',
    description: 'Invalid request parameters. Please check your input and try again.',
    action: 'Verify input parameters',
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
  SERVICE_UNAVAILABLE: {
    title: 'Service unavailable',
    description: 'Transliteration service is temporarily unavailable. Please try again in a few minutes.',
    action: 'Retry after some time',
  },
  PROCESSING_FAILED: {
    title: 'Processing failed',
    description: 'Transliteration failed. Please try again.',
    action: 'Retry',
  },
  QUOTA_EXCEEDED: {
    title: 'Quota exceeded',
    description: 'You have exceeded your usage quota for transliteration service. Please contact your administrator.',
    action: 'Contact admin or wait',
  },
  RATE_LIMIT_EXCEEDED: {
    title: 'Rate limit exceeded',
    description: 'Too many requests. Please wait before trying again.',
    action: 'Wait and retry',
  },
  MODEL_UNAVAILABLE: {
    title: 'Model unavailable',
    description: 'The selected transliteration model is currently unavailable. Please try a different model.',
    action: 'Select different model',
  },
} as const;

/** Minimum Language Detection text length (characters) to be considered valid */
export const MIN_LANGUAGE_DETECTION_TEXT_LENGTH = 2;

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
  SERVICE_UNAVAILABLE: {
    title: 'Service unavailable',
    description: 'Language detection service is temporarily unavailable. Please try again in a few minutes.',
    action: 'Retry after some time',
  },
  QUOTA_EXCEEDED: {
    title: 'Quota exceeded',
    description: 'You have exceeded your usage quota for language detection service. Please contact your administrator.',
    action: 'Contact admin or wait',
  },
  RATE_LIMIT_EXCEEDED: {
    title: 'Rate limit exceeded',
    description: 'Too many requests. Please wait before trying again.',
    action: 'Wait and retry',
  },
  MODEL_UNAVAILABLE: {
    title: 'Model unavailable',
    description: 'Language detection model is currently unavailable. Please try again later.',
    action: 'Retry later',
  },
} as const;

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

/** Audio Language Detection error codes and user-facing messages */
export const AUDIO_LANGUAGE_DETECTION_ERRORS = {
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
    description: 'This recording is too short for language detection. Please record a longer audio clip.',
    action: 'Record longer audio',
  },
  RECORDING_TOO_LONG: {
    title: 'Recording duration exceeds limit',
    description: `This recording is too long to process. Please record a shorter audio clip (max ${MAX_RECORDING_DURATION} seconds).`,
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
    description: 'This audio file is too short for language detection. Please upload a longer recording.',
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
  SERVICE_UNAVAILABLE: {
    title: 'Service unavailable',
    description: 'Audio language detection service is temporarily unavailable. Please try again in a few minutes.',
    action: 'Retry after some time',
  },
  PROCESSING_TIMEOUT: {
    title: 'Processing timeout',
    description: 'Audio processing timed out. Please try with a shorter audio file.',
    action: 'Upload shorter file',
  },
  QUOTA_EXCEEDED: {
    title: 'Quota exceeded',
    description: 'You have exceeded your usage quota for audio language detection service. Please contact your administrator.',
    action: 'Contact admin or wait',
  },
  RATE_LIMIT_EXCEEDED: {
    title: 'Rate limit exceeded',
    description: 'Too many requests. Please wait before trying again.',
    action: 'Wait and retry',
  },
  MODEL_UNAVAILABLE: {
    title: 'Model unavailable',
    description: 'Audio language detection model is currently unavailable. Please try again later.',
    action: 'Retry later',
  },
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
  SERVICE_UNAVAILABLE: {
    title: 'Service unavailable',
    description: 'Named entity recognition service is temporarily unavailable. Please try again in a few minutes.',
    action: 'Retry after some time',
  },
  PROCESSING_FAILED: {
    title: 'Processing failed',
    description: 'Entity recognition failed. Please try again.',
    action: 'Retry',
  },
  QUOTA_EXCEEDED: {
    title: 'Quota exceeded',
    description: 'You have exceeded your usage quota for NER service. Please contact your administrator.',
    action: 'Contact admin or wait',
  },
  RATE_LIMIT_EXCEEDED: {
    title: 'Rate limit exceeded',
    description: 'Too many requests. Please wait before trying again.',
    action: 'Wait and retry',
  },
  MODEL_UNAVAILABLE: {
    title: 'Model unavailable',
    description: 'The selected NER model is currently unavailable. Please try a different model.',
    action: 'Select different model',
  },
  INVALID_REQUEST: {
    title: 'Invalid request',
    description: 'Invalid request parameters. Please check your input and try again.',
    action: 'Verify input parameters',
  },
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
  SESSION_EXPIRED: {
    title: 'Session expired',
    description: 'Your session has expired. Please log in again.',
    action: 'Log in',
  },
  UNAUTHORIZED: {
    title: 'Unauthorized access',
    description: 'You don\'t have permission to access this service. Please contact your administrator.',
    action: 'Contact admin',
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

/** Common Network and System Errors (All Services) */
export const COMMON_ERRORS = {
  NETWORK_ERROR: {
    title: 'Network connection lost',
    description: 'Network connection lost. Please check your internet connection and try again.',
    action: 'Check connection',
  },
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
  FILE_TOO_LARGE: {
    title: 'File size exceeds limit',
    description: 'File size exceeds maximum limit. Please upload a smaller file.',
    action: 'Compress file',
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
  SERVICE_UNAVAILABLE: {
    title: 'Service unavailable',
    description: 'OCR service is temporarily unavailable. Please try again in a few minutes.',
    action: 'Retry after some time',
  },
  PROCESSING_TIMEOUT: {
    title: 'Processing timeout',
    description: 'Image processing timed out. Please try with a smaller file.',
    action: 'Upload smaller file',
  },
  QUOTA_EXCEEDED: {
    title: 'Quota exceeded',
    description: 'You have exceeded your usage quota for OCR service. Please contact your administrator.',
    action: 'Contact admin or wait',
  },
  RATE_LIMIT_EXCEEDED: {
    title: 'Rate limit exceeded',
    description: 'Too many requests. Please wait before trying again.',
    action: 'Wait and retry',
  },
  MODEL_UNAVAILABLE: {
    title: 'Model unavailable',
    description: 'The selected OCR model is currently unavailable. Please try a different model.',
    action: 'Select different model',
  },
  INVALID_REQUEST: {
    title: 'Invalid request',
    description: 'Invalid request parameters. Please check your input and try again.',
    action: 'Verify input parameters',
  },
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
  language: "hi", // Default to Hindi since it's in the ASR supported list
  sampleRate: 16000,
  serviceId: "asr_am_ensemble",
  audioFormat: "wav",
  encoding: "base64",
} as const;

export const DEFAULT_TTS_CONFIG = {
  language: "en",
  gender: "female",
  sampleRate: 22050,
  audioFormat: "wav",
} as const;

export const DEFAULT_NMT_CONFIG = {
  sourceLanguage: "en",
  targetLanguage: "hi",
} as const;

// API endpoints
export const API_ENDPOINTS = {
  asr: {
    inference: "/api/v1/asr/inference",
    models: "/api/v1/asr/models",
    health: "/api/v1/asr/health",
  },
  tts: {
    inference: "/api/v1/tts/inference",
    voices: "/api/v1/tts/voices",
    health: "/api/v1/tts/health",
  },
  nmt: {
    inference: "/api/v1/nmt/inference",
    models: "/api/v1/nmt/models",
    languages: "/api/v1/nmt/languages",
    health: "/api/v1/nmt/health",
  },
  pipeline: {
    inference: "/api/v1/pipeline/inference",
    info: "/api/v1/pipeline/info",
    health: "/api/v1/pipeline/health",
  },
} as const;

// WebSocket events
export const WEBSOCKET_EVENTS = {
  CONNECT: "connect",
  DISCONNECT: "disconnect",
  START: "start",
  DATA: "data",
  RESPONSE: "response",
  ERROR: "error",
} as const;
