"""
Validation Utils
Validation utility functions for request validation
"""

import logging
import re
from typing import List

logger = logging.getLogger(__name__)


class InvalidLanguageCodeError(Exception):
    """Invalid language code"""
    pass


class InvalidLanguagePairError(Exception):
    """Invalid language pair"""
    pass


class InvalidServiceIdError(Exception):
    """Invalid service ID"""
    pass


class BatchSizeExceededError(Exception):
    """Batch size exceeded"""
    pass


class InvalidTextInputError(Exception):
    """Invalid text input"""
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


class SameLanguageError(Exception):
    """Custom exception for same source and target language."""
    pass


class LanguagePairNotSupportedError(Exception):
    """Custom exception for unsupported language pair."""
    pass


# Supported languages (Indian + African languages)
SUPPORTED_LANGUAGES = [
    # Indic Languages
    "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa", 
    "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi", 
    "mai", "brx", "mni", "sat", "gom",
    # African languages (from NLLB-200 model)
    "sw", "yo", "ha", "so", "am", "ti", "ig", "zu", "xh", 
    "sn", "rw", "om", "lg", "wo", "ts", "tn", "af", "fr", "ar"
]


def validate_language_code(language_code: str) -> bool:
    """Validate language code"""
    if not language_code or len(language_code) < 2 or len(language_code) > 3:
        raise InvalidLanguageCodeError(f"Language code must be 2-3 characters: {language_code}")
    
    if language_code not in SUPPORTED_LANGUAGES:
        raise InvalidLanguageCodeError(f"Unsupported language code: {language_code}")
    
    return True


def validate_language_pair(source_lang: str, target_lang: str) -> bool:
    """Validate language pair"""
    # Validate both language codes
    validate_language_code(source_lang)
    validate_language_code(target_lang)
    
    # Check that source and target are different
    if source_lang == target_lang:
        raise SameLanguageError()
    
    return True


def validate_service_id(service_id: str) -> bool:
    """Validate service ID"""
    if not service_id or not service_id.strip():
        raise InvalidServiceIdError("Service ID cannot be empty")
    
    # Basic format validation (e.g., "ai4bharat/model-name--gpu--t4", "nllb-200-1.3B")
    if len(service_id) < 3:
        raise InvalidServiceIdError(f"Service ID too short: {service_id}")
    
    # Check for valid characters (alphanumeric, hyphens, underscores, slashes, dots)
    # Allows formats like: "ai4bharat/model-name", "nllb-200-1.3B"
    if not re.match(r'^[a-zA-Z0-9\-_/.]+$', service_id):
        raise InvalidServiceIdError(f"Service ID contains invalid characters: {service_id}")
    
    return True


def validate_batch_size(batch_size: int, max_size: int = 90) -> bool:
    """Validate batch size"""
    if batch_size < 1:
        raise BatchSizeExceededError(f"Batch size must be at least 1: {batch_size}")
    
    if batch_size > max_size:
        raise BatchSizeExceededError(f"Batch size {batch_size} exceeds maximum {max_size}")
    
    return True


def validate_text_input(text: str, min_length: int = 1, max_length: int = 10000) -> bool:
    """Validate text input for NMT processing."""
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
    
        # Check if text contains valid characters (alphanumeric or script characters)
        # This allows Indic scripts, Arabic, and other Unicode scripts
        if not re.search(r'[a-zA-Z0-9\u0900-\u097F\u0B80-\u0BFF\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F\u0980-\u09FF\u0A80-\u0AFF\u0600-\u06FF]', text_stripped):
            raise InvalidCharactersError()
    
    return True
        
    except (NoTextInputError, EmptyInputError, TextTooShortError, TextTooLongError, InvalidCharactersError):
        raise
    except Exception as e:
        logger.error(f"Text input validation failed: {e}")
        raise InvalidTextInputError(f"Text input validation failed: {e}")
