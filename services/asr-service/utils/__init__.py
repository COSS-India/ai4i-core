"""
Utils package for ASR Service.

Contains utility classes for Triton client, audio processing, and validation.
"""

from .triton_client import TritonClient
from .audio_utils import (
    validate_audio_format,
    get_audio_duration,
    convert_audio_format,
    validate_sample_rate,
    InvalidAudioFormatError,
    InvalidSampleRateError,
    AudioProcessingError
)
from .validation_utils import (
    validate_language_code,
    validate_service_id,
    validate_audio_input,
    validate_preprocessors,
    validate_postprocessors,
    InvalidLanguageCodeError,
    InvalidServiceIdError,
    InvalidAudioInputError,
    InvalidPreprocessorError,
    InvalidPostprocessorError,
    NoFileSelectedError,
    UnsupportedFormatError,
    FileTooLargeError,
    InvalidFileError,
    UploadFailedError,
    AudioTooShortError,
    AudioTooLongError,
    EmptyAudioFileError,
    UploadTimeoutError
)

__all__ = [
    # Triton client
    "TritonClient",
    
    # Audio utilities
    "validate_audio_format",
    "get_audio_duration", 
    "convert_audio_format",
    "validate_sample_rate",
    "InvalidAudioFormatError",
    "InvalidSampleRateError",
    "AudioProcessingError",
    
    # Validation utilities
    "validate_language_code",
    "validate_service_id",
    "validate_audio_input",
    "validate_preprocessors",
    "validate_postprocessors",
    "InvalidLanguageCodeError",
    "InvalidServiceIdError",
    "InvalidAudioInputError",
    "InvalidPreprocessorError",
    "InvalidPostprocessorError",
    "NoFileSelectedError",
    "UnsupportedFormatError",
    "FileTooLargeError",
    "InvalidFileError",
    "UploadFailedError",
    "AudioTooShortError",
    "AudioTooLongError",
    "EmptyAudioFileError",
    "UploadTimeoutError"
]
