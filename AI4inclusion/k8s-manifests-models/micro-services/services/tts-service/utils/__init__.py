"""
TTS Service Utils Package

This package contains utility classes and functions.
"""

from utils.triton_client import TritonClient
from utils.audio_utils import (
    validate_audio_format,
    get_audio_duration,
    convert_audio_format,
    validate_sample_rate,
    InvalidAudioFormatError,
    InvalidSampleRateError,
    AudioProcessingError
)
from utils.text_utils import (
    validate_text_length,
    detect_language,
    sanitize_text,
    estimate_audio_duration,
    TextTooLongError,
    InvalidTextError,
    UnsupportedLanguageError
)
from utils.validation_utils import (
    validate_language_code,
    validate_service_id,
    validate_gender,
    validate_audio_format as validate_audio_format_validation,
    validate_sample_rate as validate_sample_rate_validation,
    SUPPORTED_LANGUAGES,
    InvalidLanguageCodeError,
    InvalidServiceIdError,
    InvalidGenderError
)

__all__ = [
    "TritonClient",
    "validate_audio_format",
    "get_audio_duration", 
    "convert_audio_format",
    "validate_sample_rate",
    "InvalidAudioFormatError",
    "InvalidSampleRateError",
    "AudioProcessingError",
    "validate_text_length",
    "detect_language",
    "sanitize_text",
    "estimate_audio_duration",
    "TextTooLongError",
    "InvalidTextError",
    "UnsupportedLanguageError",
    "validate_language_code",
    "validate_service_id",
    "validate_gender",
    "validate_audio_format_validation",
    "validate_sample_rate_validation",
    "SUPPORTED_LANGUAGES",
    "InvalidLanguageCodeError",
    "InvalidServiceIdError",
    "InvalidGenderError"
]
