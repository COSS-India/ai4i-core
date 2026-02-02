"""
Validation utility functions for request validation.
"""

import logging
import re
import unicodedata
from typing import List

logger = logging.getLogger(__name__)


class InvalidLanguageCodeError(Exception):
    """Custom exception for invalid language codes."""
    pass


class InvalidServiceIdError(Exception):
    """Custom exception for invalid service IDs."""
    pass


class InvalidGenderError(Exception):
    """Custom exception for invalid gender values."""
    pass


class InvalidAudioFormatError(Exception):
    """Custom exception for invalid audio formats."""
    pass


class InvalidSampleRateError(Exception):
    """Custom exception for invalid sample rates."""
    pass


# Text input validation exceptions
class NoTextInputError(Exception):
    """Custom exception for missing text input."""
    pass


class TextTooShortError(Exception):
    """Custom exception for text that is too short."""
    pass


class TextTooLongError(Exception):
    """Custom exception for text that is too long."""
    pass


class InvalidCharactersError(Exception):
    """Custom exception for invalid characters in text."""
    pass


class EmptyInputError(Exception):
    """Custom exception for empty text input."""
    pass


class LanguageMismatchError(Exception):
    """Custom exception for language mismatch."""
    pass


class VoiceNotAvailableError(Exception):
    """Custom exception for unavailable voice."""
    pass


# Supported languages constant
SUPPORTED_LANGUAGES = [
    "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa", 
    "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi", "mai", 
    "brx", "mni"
]


def validate_language_code(language_code: str) -> bool:
    """Validate language code is supported."""
    try:
        if not language_code or len(language_code) < 2 or len(language_code) > 3:
            raise InvalidLanguageCodeError("Language code must be 2-3 characters")
        
        if language_code not in SUPPORTED_LANGUAGES:
            raise InvalidLanguageCodeError(
                f"Language code '{language_code}' not supported. "
                f"Supported languages: {', '.join(SUPPORTED_LANGUAGES)}"
            )
        
        return True
        
    except InvalidLanguageCodeError:
        raise
    except Exception as e:
        logger.error(f"Language code validation failed: {e}")
        raise InvalidLanguageCodeError(f"Language code validation failed: {e}")


def validate_service_id(service_id: str) -> bool:
    """Validate service ID format."""
    try:
        if not service_id or not service_id.strip():
            raise InvalidServiceIdError("Service ID cannot be empty")
        
        # Basic format validation (e.g., "ai4bharat/model-name--gpu--t4")
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9\-_/]*[a-zA-Z0-9]$', service_id):
            raise InvalidServiceIdError(
                "Service ID must contain only alphanumeric characters, hyphens, underscores, and forward slashes"
            )
        
        return True
        
    except InvalidServiceIdError:
        raise
    except Exception as e:
        logger.error(f"Service ID validation failed: {e}")
        raise InvalidServiceIdError(f"Service ID validation failed: {e}")


def validate_gender(gender: str) -> bool:
    """Validate gender value."""
    try:
        if gender not in ["male", "female"]:
            raise InvalidGenderError(f"Gender must be 'male' or 'female', got '{gender}'")
        
        return True
        
    except InvalidGenderError:
        raise
    except Exception as e:
        logger.error(f"Gender validation failed: {e}")
        raise InvalidGenderError(f"Gender validation failed: {e}")


def validate_audio_format(audio_format: str) -> bool:
    """Validate audio format is supported."""
    try:
        supported_formats = ["wav", "mp3", "ogg", "pcm"]
        
        if audio_format not in supported_formats:
            raise InvalidAudioFormatError(
                f"Audio format '{audio_format}' not supported. "
                f"Supported formats: {', '.join(supported_formats)}"
            )
        
        return True
        
    except InvalidAudioFormatError:
        raise
    except Exception as e:
        logger.error(f"Audio format validation failed: {e}")
        raise InvalidAudioFormatError(f"Audio format validation failed: {e}")


def validate_sample_rate(sample_rate: int) -> bool:
    """Validate sample rate is in valid range."""
    try:
        # Common sample rates
        common_rates = [8000, 16000, 22050, 44100, 48000]
        
        if sample_rate in common_rates:
            return True
        
        # Check if it's in a reasonable range
        if not (8000 <= sample_rate <= 48000):
            raise InvalidSampleRateError(
                f"Sample rate {sample_rate} not supported. "
                f"Common rates: {common_rates} or 8000-48000 Hz"
            )
        
        return True
        
    except InvalidSampleRateError:
        raise
    except Exception as e:
        logger.error(f"Sample rate validation failed: {e}")
        raise InvalidSampleRateError(f"Sample rate validation failed: {e}")


def validate_text_input(text: str, min_length: int = 1, max_length: int = 5000) -> bool:
    """Validate text input for TTS processing."""
    try:
        # Check if text is provided or empty
        if text is None or not text or not text.strip():
            raise NoTextInputError()
        
        text_stripped = text.strip()
        
        # Check minimum length
        if len(text_stripped) < min_length:
            raise TextTooShortError()
        
        # Check maximum length
        if len(text_stripped) > max_length:
            raise TextTooLongError()
        
        # Check if text contains at least one Unicode letter (works for any language script)
        # This allows pure local language text (Hindi, Tamil, Telugu, etc.) without requiring English letters
        has_letter = False
        invalid_chars = []
        for char in text_stripped:
            if unicodedata.category(char).startswith('L'):  # 'L' means Letter category
                has_letter = True
            # Check for invalid characters (control characters except whitespace)
            elif unicodedata.category(char).startswith('C') and char not in ['\n', '\r', '\t', ' ']:
                invalid_chars.append(char)
        
        if invalid_chars:
            raise InvalidCharactersError()
        
        if not has_letter:
            raise TextTooShortError()  # No meaningful content
        
        return True
        
    except (NoTextInputError, EmptyInputError, TextTooShortError, TextTooLongError, InvalidCharactersError):
        raise
    except Exception as e:
        logger.error(f"Text input validation failed: {e}")
        raise ValueError(f"Text input validation failed: {e}")


def validate_audio_duration(audio_duration: float) -> bool:
    """Validate audio duration is reasonable."""
    try:
        if audio_duration <= 0:
            raise ValueError("Audio duration must be positive")
        
        if audio_duration > 300:  # 5 minutes max
            raise ValueError("Audio duration cannot exceed 300 seconds")
        
        return True
        
    except ValueError as e:
        logger.error(f"Audio duration validation failed: {e}")
        raise ValueError(f"Audio duration validation failed: {e}")
    except Exception as e:
        logger.error(f"Audio duration validation failed: {e}")
        raise ValueError(f"Audio duration validation failed: {e}")
