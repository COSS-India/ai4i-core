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


# Supported languages for transliteration
SUPPORTED_LANGUAGES = [
    # Indic Languages
    "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa", 
    "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi", 
    "mai", "brx", "mni", "sat", "gom"
]


def validate_language_code(language_code: str) -> bool:
    """Validate language code"""
    if not language_code or len(language_code) < 2 or len(language_code) > 3:
        raise InvalidLanguageCodeError(f"Language code must be 2-3 characters: {language_code}")
    
    if language_code not in SUPPORTED_LANGUAGES:
        logger.warning(f"Language code '{language_code}' not in supported list, but allowing it")
        # Allow it anyway - Triton model may support more languages
    
    return True


def validate_language_pair(source_lang: str, target_lang: str) -> bool:
    """Validate language pair"""
    # Validate both language codes
    validate_language_code(source_lang)
    validate_language_code(target_lang)
    
    # For transliteration, source and target can be the same (e.g., en->en for different scripts)
    # So we don't enforce different languages like we do for translation
    
    return True


def validate_service_id(service_id: str) -> bool:
    """Validate service ID"""
    if not service_id or not service_id.strip():
        raise InvalidServiceIdError("Service ID cannot be empty")
    
    # Basic format validation
    if len(service_id) < 3:
        raise InvalidServiceIdError(f"Service ID too short: {service_id}")
    
    # Check for valid characters (alphanumeric, hyphens, underscores, slashes, dots)
    if not re.match(r'^[a-zA-Z0-9\-_/.]+$', service_id):
        raise InvalidServiceIdError(f"Service ID contains invalid characters: {service_id}")
    
    return True


def validate_batch_size(batch_size: int, max_size: int = 100) -> bool:
    """Validate batch size"""
    if batch_size < 1:
        raise BatchSizeExceededError(f"Batch size must be at least 1: {batch_size}")
    
    if batch_size > max_size:
        raise BatchSizeExceededError(f"Batch size {batch_size} exceeds maximum {max_size}")
    
    return True


def validate_text_input(text: str) -> bool:
    """Validate text input"""
    if text is None:
        raise InvalidTextInputError("Text input cannot be None")
    
    # Allow empty strings for transliteration (service handles this)
    
    if len(text) > 10000:
        raise InvalidTextInputError(f"Text input too long: {len(text)} characters")
    
    return True

