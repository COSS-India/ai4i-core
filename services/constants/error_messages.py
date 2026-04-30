"""
Error messages and error codes for all services.

This module contains centralized error codes and messages used across all services
for consistent error handling and user feedback.
"""

# ============================================================================
# ASR Service Error Codes
# ============================================================================

# Error Codes
LANGUAGE_NOT_SUPPORTED = "LANGUAGE_NOT_SUPPORTED"
SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
PROCESSING_TIMEOUT = "PROCESSING_TIMEOUT"
QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
POOR_AUDIO_QUALITY = "POOR_AUDIO_QUALITY"
INVALID_REQUEST = "INVALID_REQUEST"
AUTH_FAILED = "AUTH_FAILED"
TENANT_SUSPENDED = "TENANT_SUSPENDED"
INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
NO_FILE_SELECTED = "NO_FILE_SELECTED"
UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
FILE_TOO_LARGE = "FILE_TOO_LARGE"
INVALID_FILE = "INVALID_FILE"
UPLOAD_FAILED = "UPLOAD_FAILED"
AUDIO_TOO_SHORT = "AUDIO_TOO_SHORT"
AUDIO_TOO_LONG = "AUDIO_TOO_LONG"
EMPTY_AUDIO_FILE = "EMPTY_AUDIO_FILE"
UPLOAD_TIMEOUT = "UPLOAD_TIMEOUT"

# Error Messages
LANGUAGE_NOT_SUPPORTED_MESSAGE = "Uploaded audio language doesn't match selected language. Upload audio in selected language."
SERVICE_UNAVAILABLE_MESSAGE = "ASR service is temporarily unavailable. Please try again in a few minutes."
PROCESSING_TIMEOUT_MESSAGE = "Audio processing timed out. Please try with a shorter audio file or try again later."
QUOTA_EXCEEDED_MESSAGE = "You have exceeded your usage quota for ASR service. Please contact your administrator or try again tomorrow."
MODEL_UNAVAILABLE_MESSAGE = "The selected ASR model is currently unavailable. Please try a different model or contact support."
RATE_LIMIT_EXCEEDED_MESSAGE = "Too many requests. Please wait {x} seconds before trying again."
POOR_AUDIO_QUALITY_MESSAGE = "Audio quality is too poor for accurate transcription. Please provide clearer audio."
INVALID_REQUEST_MESSAGE = "Invalid request parameters. Please check your input and try again."
AUTH_FAILED_MESSAGE = "Authentication failed. Please log in again."
TENANT_SUSPENDED_MESSAGE = "Your account access has been suspended. Please contact support."
INTERNAL_SERVER_ERROR_MESSAGE = "Internal server error. Please try again later."
NO_FILE_SELECTED_MESSAGE = "Please select an audio file to upload."
UNSUPPORTED_FORMAT_MESSAGE = "File format not supported. Please upload audio files in WAV, or MP3 format."
FILE_TOO_LARGE_MESSAGE = "File size exceeds maximum limit. Please upload a smaller file."
INVALID_FILE_MESSAGE = "The uploaded file appears to be corrupted or invalid. Please try a different file."
UPLOAD_FAILED_MESSAGE = "File upload failed. Please check your internet connection and try again."
AUDIO_TOO_SHORT_MESSAGE = "Audio file must be at least 1 second long. Please upload a longer audio file."
AUDIO_TOO_LONG_MESSAGE = "Audio file exceeds maximum duration of 60 seconds. Please upload a shorter file."
EMPTY_AUDIO_FILE_MESSAGE = "Unable to detect audio in this file. Please upload a file with audible content."
UPLOAD_TIMEOUT_MESSAGE = "Upload timed out. Please check your internet connection and try again."

# ============================================================================
# TTS Service Error Codes
# ============================================================================

# Text Input Error Codes
NO_TEXT_INPUT = "NO_TEXT_INPUT"
TEXT_TOO_SHORT = "TEXT_TOO_SHORT"
TEXT_TOO_LONG = "TEXT_TOO_LONG"
INVALID_CHARACTERS = "INVALID_CHARACTERS"
EMPTY_INPUT = "EMPTY_INPUT"
LANGUAGE_MISMATCH = "LANGUAGE_MISMATCH"
VOICE_NOT_AVAILABLE = "VOICE_NOT_AVAILABLE"
PROCESSING_FAILED = "PROCESSING_FAILED"
AUDIO_GEN_FAILED = "AUDIO_GEN_FAILED"

# Audio Output Error Codes
PLAYBACK_FAILED = "PLAYBACK_FAILED"
DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
AUDIO_FORMAT_ERROR = "AUDIO_FORMAT_ERROR"

# Text Input Error Messages
NO_TEXT_INPUT_MESSAGE = "Please enter text to convert to speech."
TEXT_TOO_SHORT_MESSAGE = "Please provide sufficient text to convert."
TEXT_TOO_LONG_MESSAGE = "Text exceeds maximum limit. Please reduce the text length."
INVALID_CHARACTERS_MESSAGE = "Text contains invalid characters. Please use only alphanumeric characters and punctuation."
EMPTY_INPUT_MESSAGE = "Text input cannot be empty. Please enter some text."
LANGUAGE_MISMATCH_MESSAGE = "The text language doesn't match the selected language. Please select the correct language."

# TTS Service Error Messages
LANGUAGE_NOT_SUPPORTED_TTS_MESSAGE = "The selected language is not supported for TTS. Please choose from: Hindi, English, Tamil, Telugu, Bengali."
VOICE_NOT_AVAILABLE_MESSAGE = "The selected voice is not available for this language. Please choose a different voice."
SERVICE_UNAVAILABLE_TTS_MESSAGE = "TTS service is temporarily unavailable. Please try again in a few minutes."
PROCESSING_FAILED_MESSAGE = "Failed to generate speech. Please try again."
QUOTA_EXCEEDED_TTS_MESSAGE = "You have exceeded your usage quota for TTS service. Please contact your administrator or try again tomorrow."
RATE_LIMIT_EXCEEDED_TTS_MESSAGE = "Too many requests. Please wait {x} seconds before trying again."
MODEL_UNAVAILABLE_TTS_MESSAGE = "The selected TTS model is currently unavailable. Please try a different model."
AUDIO_GEN_FAILED_MESSAGE = "Audio generation failed. Please try again or contact support if the issue persists."
INVALID_REQUEST_TTS_MESSAGE = "Invalid request parameters. Please check your input and try again."
AUTH_FAILED_TTS_MESSAGE = "Authentication failed. Please log in again."
TENANT_SUSPENDED_TTS_MESSAGE = "Your account access has been suspended. Please contact support."

# Audio Output Error Messages
PLAYBACK_FAILED_MESSAGE = "Unable to play generated audio. Please try regenerating or download the file."
DOWNLOAD_FAILED_MESSAGE = "Failed to download audio file. Please try again."
AUDIO_FORMAT_ERROR_MESSAGE = "Generated audio format is not supported by your browser. Please try downloading instead."

# ============================================================================
# NMT Service Error Codes
# ============================================================================

# NMT-specific Error Codes (some text input codes already defined above)
SAME_LANGUAGE_ERROR = "SAME_LANGUAGE_ERROR"
LANGUAGE_PAIR_NOT_SUPPORTED = "LANGUAGE_PAIR_NOT_SUPPORTED"
TRANSLATION_FAILED = "TRANSLATION_FAILED"

# NMT Text Input Error Messages (reusing codes, but NMT-specific messages)
NO_TEXT_INPUT_NMT_MESSAGE = "Please enter text to translate."
TEXT_TOO_SHORT_NMT_MESSAGE = "Please provide sufficient text to translate."
TEXT_TOO_LONG_NMT_MESSAGE = "Text exceeds maximum limit. Please reduce the text length."
INVALID_CHARACTERS_NMT_MESSAGE = "Text contains unsupported characters. Please remove special symbols and try again."
EMPTY_INPUT_NMT_MESSAGE = "Text input cannot be empty. Please enter some text."

# NMT Service Error Messages
SAME_LANGUAGE_ERROR_MESSAGE = "Source and target languages cannot be the same. Please select different languages."
LANGUAGE_PAIR_NOT_SUPPORTED_MESSAGE = "Translation from {source} to {target} is not supported. Please check available language pairs."
SERVICE_UNAVAILABLE_NMT_MESSAGE = "Translation service is temporarily unavailable. Please try again in a few minutes."
TRANSLATION_FAILED_MESSAGE = "Translation failed. Please try again."
QUOTA_EXCEEDED_NMT_MESSAGE = "You have exceeded your usage quota for translation service. Please contact your administrator."
RATE_LIMIT_EXCEEDED_NMT_MESSAGE = "Too many requests. Please wait {x} seconds before trying again."
MODEL_UNAVAILABLE_NMT_MESSAGE = "The selected translation model is currently unavailable. Please try a different model."
INVALID_REQUEST_NMT_MESSAGE = "Invalid request parameters. Please check your input and try again."
AUTH_FAILED_NMT_MESSAGE = "Authentication failed. Please log in again."
TENANT_SUSPENDED_NMT_MESSAGE = "Your account access has been suspended. Please contact support."

# ============================================================================
# Auth Service Error Codes
# ============================================================================

# Auth Service Error Codes
AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
SESSION_EXPIRED = "SESSION_EXPIRED"
UNAUTHORIZED = "UNAUTHORIZED"

# Auth Service Error Messages
AUTHENTICATION_REQUIRED_MESSAGE = "Authentication is required to access this service. Please log in."
INVALID_CREDENTIALS_MESSAGE = "Invalid credentials provided. Please log in again."
SESSION_EXPIRED_MESSAGE = "Your session has expired. Please log in again."
UNAUTHORIZED_MESSAGE = "You don't have permission to access this service. Please contact your administrator."
