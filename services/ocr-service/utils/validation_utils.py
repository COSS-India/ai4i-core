"""
Validation utilities for OCR service.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class InvalidServiceIdError(ValueError):
    """Exception raised for invalid service ID."""
    pass


class InvalidLanguageCodeError(ValueError):
    """Exception raised for invalid language code."""
    pass


def validate_service_id(service_id: str) -> bool:
    """
    Validate service ID format.
    
    Args:
        service_id: Service ID to validate
        
    Returns:
        True if valid
        
    Raises:
        InvalidServiceIdError: If service ID is invalid
    """
    if not service_id or not service_id.strip():
        raise InvalidServiceIdError("Service ID cannot be empty")
    
    # Basic format validation (e.g., "ai4bharat/surya-ocr-v1--gpu--t4")
    if len(service_id) < 3:
        raise InvalidServiceIdError(f"Service ID too short: {service_id}")
    
    # Check for valid characters (alphanumeric, hyphens, underscores, slashes, dots)
    if not re.match(r'^[a-zA-Z0-9\-_/.]+$', service_id):
        raise InvalidServiceIdError(f"Service ID contains invalid characters: {service_id}")
    
    return True


def validate_language_code(language_code: str) -> bool:
    """
    Validate language code format.
    
    Args:
        language_code: Language code to validate (e.g., 'en', 'hi', 'ta')
        
    Returns:
        True if valid
        
    Raises:
        InvalidLanguageCodeError: If language code is invalid
    """
    if not language_code or not language_code.strip():
        raise InvalidLanguageCodeError("Language code cannot be empty")
    
    # Basic validation: 2-3 letter ISO 639 codes
    if not re.match(r'^[a-z]{2,3}$', language_code.lower()):
        raise InvalidLanguageCodeError(f"Invalid language code format: {language_code}")
    
    return True

