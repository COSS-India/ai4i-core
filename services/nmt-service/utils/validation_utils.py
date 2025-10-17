"""
Validation Utils
Validation utility functions for request validation
"""

import logging
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


# Supported languages
SUPPORTED_LANGUAGES = [
    "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa", 
    "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi", 
    "mai", "brx", "mni"
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
        raise InvalidLanguagePairError(f"Source and target languages must be different: {source_lang}")
    
    return True


def validate_service_id(service_id: str) -> bool:
    """Validate service ID"""
    if not service_id or not service_id.strip():
        raise InvalidServiceIdError("Service ID cannot be empty")
    
    # Basic format validation (e.g., "ai4bharat/model-name--gpu--t4")
    if len(service_id) < 3:
        raise InvalidServiceIdError(f"Service ID too short: {service_id}")
    
    # Check for valid characters (alphanumeric, hyphens, underscores, slashes)
    if not re.match(r'^[a-zA-Z0-9\-_/]+$', service_id):
        raise InvalidServiceIdError(f"Service ID contains invalid characters: {service_id}")
    
    return True


def validate_batch_size(batch_size: int, max_size: int = 90) -> bool:
    """Validate batch size"""
    if batch_size < 1:
        raise BatchSizeExceededError(f"Batch size must be at least 1: {batch_size}")
    
    if batch_size > max_size:
        raise BatchSizeExceededError(f"Batch size {batch_size} exceeds maximum {max_size}")
    
    return True


def validate_text_input(text: str) -> bool:
    """Validate text input"""
    if not text or not text.strip():
        raise InvalidTextInputError("Text input cannot be empty")
    
    if len(text) > 10000:
        raise InvalidTextInputError(f"Text input too long: {len(text)} characters")
    
    # Check if text contains only special characters
    if not re.search(r'[a-zA-Z0-9\u0900-\u097F\u0B80-\u0BFF\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F\u0980-\u09FF\u0A80-\u0AFF\u0600-\u06FF]', text):
        raise InvalidTextInputError("Text input must contain at least some alphanumeric or script characters")
    
    return True
