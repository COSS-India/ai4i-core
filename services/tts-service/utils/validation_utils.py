"""
Validation utility functions for request validation.
"""

import logging
import re
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


def validate_text_input(text: str) -> bool:
    """Validate text input for TTS processing."""
    try:
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")
        
        if len(text) > 5000:
            raise ValueError("Text cannot exceed 5000 characters")
        
        # Check for reasonable content
        if not re.search(r'[a-zA-Z\u0900-\u097F\u0A80-\u0AFF\u0B00-\u0B7F\u0B80-\u0BFF\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F\u0D80-\u0DFF\u0E00-\u0E7F\u0E80-\u0EFF\u0F00-\u0FFF]', text):
            raise ValueError("Text must contain at least some alphabetic characters")
        
        return True
        
    except ValueError as e:
        logger.error(f"Text input validation failed: {e}")
        raise ValueError(f"Text input validation failed: {e}")
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
