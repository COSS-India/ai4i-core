"""
Text Service
Text processing utilities for transliteration
"""

import re
import unicodedata
import logging
from typing import List

logger = logging.getLogger(__name__)


class TextTooLongError(Exception):
    """Text exceeds maximum length"""
    pass


class InvalidTextError(Exception):
    """Invalid text input"""
    pass


class TextService:
    """Service for text processing and normalization"""
    
    def __init__(self):
        pass
    
    def normalize_text(self, text: str) -> str:
        """Normalize text for processing"""
        try:
            # Replace newlines with spaces
            text = text.replace("\n", " ")
            
            # Strip leading/trailing whitespace
            text = text.strip()
            
            # Remove multiple consecutive spaces
            text = re.sub(r'\s+', ' ', text)
            
            return text
            
        except Exception as e:
            logger.error(f"Failed to normalize text: {e}")
            raise InvalidTextError(f"Failed to normalize text: {e}")
    
    def validate_text_length(self, text: str, max_length: int = 10000) -> bool:
        """Validate text length"""
        if len(text) > max_length:
            raise TextTooLongError(f"Text length {len(text)} exceeds maximum {max_length}")
        return True
    
    def detect_language(self, text: str) -> str:
        """Basic language detection using Unicode ranges"""
        try:
            # Check for Devanagari script (Hindi, Marathi, Sanskrit)
            if any('\u0900' <= char <= '\u097F' for char in text):
                return "hi"
            
            # Check for Tamil script
            if any('\u0B80' <= char <= '\u0BFF' for char in text):
                return "ta"
            
            # Check for Telugu script
            if any('\u0C00' <= char <= '\u0C7F' for char in text):
                return "te"
            
            # Check for Kannada script
            if any('\u0C80' <= char <= '\u0CFF' for char in text):
                return "kn"
            
            # Check for Malayalam script
            if any('\u0D00' <= char <= '\u0D7F' for char in text):
                return "ml"
            
            # Check for Bengali script
            if any('\u0980' <= char <= '\u09FF' for char in text):
                return "bn"
            
            # Check for Gujarati script
            if any('\u0A80' <= char <= '\u0AFF' for char in text):
                return "gu"
            
            # Check for Arabic script (Urdu)
            if any('\u0600' <= char <= '\u06FF' for char in text):
                return "ur"
            
            # Default to English for Latin script
            return "en"
            
        except Exception as e:
            logger.error(f"Failed to detect language: {e}")
            return "en"  # Default fallback
    
    def sanitize_text(self, text: str) -> str:
        """Sanitize text by removing control characters"""
        try:
            # Remove control characters except newline and tab
            text = ''.join(char for char in text if unicodedata.category(char)[0] != 'C' or char in '\n\t')
            
            # Remove zero-width characters
            text = re.sub(r'[\u200b-\u200d\ufeff]', '', text)
            
            # Normalize Unicode (NFC normalization)
            text = unicodedata.normalize('NFC', text)
            
            return text
            
        except Exception as e:
            logger.error(f"Failed to sanitize text: {e}")
            raise InvalidTextError(f"Failed to sanitize text: {e}")
    
    def split_long_text(self, text: str, max_length: int = 5000) -> List[str]:
        """Split long text into chunks"""
        try:
            if len(text) <= max_length:
                return [text]
            
            # Split on sentence boundaries
            sentences = re.split(r'[.!?।]', text)
            
            chunks = []
            current_chunk = ""
            
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                
                # Add sentence ending back
                if sentence and not sentence.endswith(('.', '!', '?', '।')):
                    sentence += '.'
                
                if len(current_chunk) + len(sentence) + 1 <= max_length:
                    if current_chunk:
                        current_chunk += " " + sentence
                    else:
                        current_chunk = sentence
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = sentence
            
            if current_chunk:
                chunks.append(current_chunk)
            
            return chunks if chunks else [text]
            
        except Exception as e:
            logger.error(f"Failed to split text: {e}")
            return [text]  # Return original text as single chunk

