"""
Text Utils
Text utility functions for validation and processing
"""

import re
import unicodedata
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TextTooLongError(Exception):
    """Text exceeds maximum length"""
    pass


class InvalidTextError(Exception):
    """Invalid text input"""
    pass


# Language code to script code mapping
LANG_CODE_TO_SCRIPT_CODE = {
    "hi": "Deva", "ur": "Arab", "ta": "Taml", "te": "Telu", 
    "kn": "Knda", "ml": "Mlym", "bn": "Beng", "gu": "Gujr", 
    "mr": "Deva", "pa": "Guru", "or": "Orya", "as": "Beng"
}


def validate_text_length(text: str, max_length: int = 10000) -> bool:
    """Validate text length"""
    if len(text) > max_length:
        raise TextTooLongError(f"Text length {len(text)} exceeds maximum {max_length}")
    return True


def detect_script(text: str) -> str:
    """Detect script from text using Unicode ranges"""
    try:
        # Check for Devanagari script (Hindi, Marathi, Sanskrit)
        if any('\u0900' <= char <= '\u097F' for char in text):
            return "Deva"
        
        # Check for Arabic script (Urdu)
        if any('\u0600' <= char <= '\u06FF' for char in text):
            return "Arab"
        
        # Check for Tamil script
        if any('\u0B80' <= char <= '\u0BFF' for char in text):
            return "Taml"
        
        # Check for Telugu script
        if any('\u0C00' <= char <= '\u0C7F' for char in text):
            return "Telu"
        
        # Check for Kannada script
        if any('\u0C80' <= char <= '\u0CFF' for char in text):
            return "Knda"
        
        # Check for Malayalam script
        if any('\u0D00' <= char <= '\u0D7F' for char in text):
            return "Mlym"
        
        # Check for Bengali script
        if any('\u0980' <= char <= '\u09FF' for char in text):
            return "Beng"
        
        # Check for Gujarati script
        if any('\u0A80' <= char <= '\u0AFF' for char in text):
            return "Gujr"
        
        # Check for Gurmukhi script (Punjabi)
        if any('\u0A00' <= char <= '\u0A7F' for char in text):
            return "Guru"
        
        # Check for Oriya script
        if any('\u0B00' <= char <= '\u0B7F' for char in text):
            return "Orya"
        
        # Default to Latin script
        return "Latn"
        
    except Exception as e:
        logger.error(f"Failed to detect script: {e}")
        return "Latn"  # Default fallback


def sanitize_text(text: str) -> str:
    """Sanitize text by removing control characters"""
    try:
        # Remove control characters except newline and tab
        text = ''.join(char for char in text if unicodedata.category(char)[0] != 'C' or char in '\n\t')
        
        # Remove zero-width characters
        text = re.sub(r'[\u200b-\u200d\ufeff]', '', text)
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
        
    except Exception as e:
        logger.error(f"Failed to sanitize text: {e}")
        raise InvalidTextError(f"Failed to sanitize text: {e}")


def count_words(text: str) -> int:
    """Count words in text"""
    try:
        # Split on whitespace and count non-empty tokens
        words = [word for word in text.split() if word.strip()]
        return len(words)
        
    except Exception as e:
        logger.error(f"Failed to count words: {e}")
        return 0


def estimate_translation_time(text: str, words_per_second: float = 50.0) -> float:
    """Estimate translation time based on word count"""
    try:
        word_count = count_words(text)
        time_estimate = word_count / words_per_second
        
        # Add 20% buffer
        time_estimate *= 1.2
        
        return time_estimate
        
    except Exception as e:
        logger.error(f"Failed to estimate translation time: {e}")
        return 1.0  # Default 1 second fallback


class TextUtils:
    """Text utility class for common text operations"""
    
    @staticmethod
    def validate_text(text: str, max_length: int = 10000) -> bool:
        """Validate text input"""
        return validate_text(text, max_length)
    
    @staticmethod
    def clean_text(text: str) -> str:
        """Clean text input"""
        return clean_text(text)
    
    @staticmethod
    def detect_language(text: str) -> Optional[str]:
        """Detect language of text"""
        return detect_language(text)
    
    @staticmethod
    def estimate_translation_time(text: str, source_lang: str, target_lang: str) -> float:
        """Estimate translation time"""
        return estimate_translation_time(text, source_lang, target_lang)
