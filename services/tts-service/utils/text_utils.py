"""
Text utility functions for validation and processing.
"""

import re
import unicodedata
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TextTooLongError(Exception):
    """Custom exception for text that exceeds maximum length."""
    pass


class InvalidTextError(Exception):
    """Custom exception for invalid text input."""
    pass


class UnsupportedLanguageError(Exception):
    """Custom exception for unsupported language codes."""
    pass


def validate_text_length(text: str, max_length: int = 5000) -> bool:
    """Validate text length is within limits."""
    try:
        if len(text) > max_length:
            raise TextTooLongError(f"Text length {len(text)} exceeds maximum {max_length}")
        return True
    except TextTooLongError:
        raise
    except Exception as e:
        logger.error(f"Text length validation failed: {e}")
        raise InvalidTextError(f"Text length validation failed: {e}")


def detect_language(text: str) -> str:
    """
    Detect language from text using Unicode ranges.
    
    Basic language detection - full detection deferred to Phase 2.
    """
    try:
        # Check for Devanagari script (Hindi, Marathi, etc.)
        if re.search(r'[\u0900-\u097F]', text):
            return "hi"  # Default to Hindi
        
        # Check for Tamil script
        if re.search(r'[\u0B80-\u0BFF]', text):
            return "ta"
        
        # Check for Telugu script
        if re.search(r'[\u0C00-\u0C7F]', text):
            return "te"
        
        # Check for Kannada script
        if re.search(r'[\u0C80-\u0CFF]', text):
            return "kn"
        
        # Check for Malayalam script
        if re.search(r'[\u0D00-\u0D7F]', text):
            return "ml"
        
        # Check for Bengali script
        if re.search(r'[\u0980-\u09FF]', text):
            return "bn"
        
        # Check for Gujarati script
        if re.search(r'[\u0A80-\u0AFF]', text):
            return "gu"
        
        # Check for Punjabi script (Gurmukhi)
        if re.search(r'[\u0A00-\u0A7F]', text):
            return "pa"
        
        # Check for Odia script
        if re.search(r'[\u0B00-\u0B7F]', text):
            return "or"
        
        # Check for Assamese script
        if re.search(r'[\u0980-\u09FF]', text) and re.search(r'[\u09F0-\u09FF]', text):
            return "as"
        
        # Check for Urdu script (Arabic)
        if re.search(r'[\u0600-\u06FF]', text):
            return "ur"
        
        # Check for Sanskrit script (Devanagari)
        if re.search(r'[\u0900-\u097F]', text) and re.search(r'[\u1CD0-\u1CFF]', text):
            return "sa"
        
        # Check for Kashmiri script (Arabic)
        if re.search(r'[\u0600-\u06FF]', text) and re.search(r'[\u0671-\u0672]', text):
            return "ks"
        
        # Check for Nepali script (Devanagari)
        if re.search(r'[\u0900-\u097F]', text) and re.search(r'[\u0901-\u0903]', text):
            return "ne"
        
        # Check for Sindhi script (Arabic)
        if re.search(r'[\u0600-\u06FF]', text) and re.search(r'[\u06AA-\u06AB]', text):
            return "sd"
        
        # Check for Konkani script (Devanagari)
        if re.search(r'[\u0900-\u097F]', text) and re.search(r'[\u0901-\u0903]', text):
            return "kok"
        
        # Check for Dogri script (Devanagari)
        if re.search(r'[\u0900-\u097F]', text) and re.search(r'[\u0901-\u0903]', text):
            return "doi"
        
        # Check for Maithili script (Devanagari)
        if re.search(r'[\u0900-\u097F]', text) and re.search(r'[\u0901-\u0903]', text):
            return "mai"
        
        # Check for Bodo script (Devanagari)
        if re.search(r'[\u0900-\u097F]', text) and re.search(r'[\u0901-\u0903]', text):
            return "brx"
        
        # Check for Manipuri script (Meitei Mayek)
        if re.search(r'[\uABC0-\uABFF]', text):
            return "mni"
        
        # Default to English for Latin script
        if re.search(r'[a-zA-Z]', text):
            return "en"
        
        # Unknown language
        return "unknown"
        
    except Exception as e:
        logger.error(f"Language detection failed: {e}")
        return "unknown"


def sanitize_text(text: str) -> str:
    """Sanitize text by removing control characters and normalizing."""
    try:
        # Remove control characters (except newline, tab)
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
        
        # Remove zero-width characters
        text = re.sub(r'[\u200B-\u200D\uFEFF]', '', text)
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        return text
        
    except Exception as e:
        logger.error(f"Text sanitization failed: {e}")
        raise InvalidTextError(f"Text sanitization failed: {e}")


def estimate_audio_duration(text: str, language: str = "en", speaking_rate: float = 150.0) -> float:
    """
    Estimate audio duration for given text.
    
    This is a rough estimation - actual duration depends on TTS model.
    """
    try:
        # Count words
        word_count = len(text.split())
        
        # Estimate duration: words per minute to seconds
        duration = (word_count / speaking_rate) * 60
        
        # Add buffer for pauses
        duration *= 1.2
        
        return duration
        
    except Exception as e:
        logger.error(f"Duration estimation failed: {e}")
        return 0.0
