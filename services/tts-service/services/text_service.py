"""
Text processing service with utilities for text manipulation and SSML support.

Adapted from Dhruva-Platform-2 inference_service.py text processing methods.
"""

import re
import unicodedata
import logging
from typing import List, Tuple, Dict, Any

logger = logging.getLogger(__name__)


class TextProcessingError(Exception):
    """Custom exception for text processing errors."""
    pass


class InvalidTextError(TextProcessingError):
    """Exception for invalid text input."""
    pass


class TextService:
    """Text processing service for TTS operations."""
    
    def __init__(self):
        """Initialize text service."""
        pass
    
    def process_tts_input(self, text: str) -> str:
        """
        Process TTS input text for normalization.
        
        Adapted from Dhruva-Platform-2 __process_tts_input method (lines 934-936).
        """
        try:
            # Replace "।" (Devanagari danda) with "."
            processed_text = text.replace("।", ".")
            
            # Strip leading/trailing whitespace
            processed_text = processed_text.strip()
            
            # Remove multiple consecutive spaces
            processed_text = re.sub(r'\s+', ' ', processed_text)
            
            return processed_text
            
        except Exception as e:
            logger.error(f"Text processing failed: {e}")
            raise TextProcessingError(f"Failed to process text: {e}")
    
    def chunk_text(self, text: str, max_length: int = 400) -> List[str]:
        """
        Split long text into smaller chunks for TTS processing.
        
        Adapted from Dhruva-Platform-2 text chunking logic (lines 506-518).
        """
        try:
            if len(text) <= max_length:
                return [text]
            
            # Split text into words
            words = text.split(" ")
            chunks = []
            tmp_sent = ""
            
            for word in words:
                # Check if adding this word would exceed max_length
                if len(tmp_sent) + len(word) + 1 <= max_length:  # +1 for space
                    if tmp_sent:
                        tmp_sent += " " + word
                    else:
                        tmp_sent = word
                else:
                    # Add current chunk and start new one
                    if tmp_sent:
                        chunks.append(tmp_sent)
                    tmp_sent = word
            
            # Add final chunk
            if tmp_sent:
                chunks.append(tmp_sent)
            
            return chunks
            
        except Exception as e:
            logger.error(f"Text chunking failed: {e}")
            raise TextProcessingError(f"Failed to chunk text: {e}")
    
    def parse_ssml(self, text: str) -> Tuple[str, Dict[str, Any]]:
        """
        Parse SSML tags and extract attributes.
        
        Basic SSML support for Phase 1 - full support deferred to Phase 2.
        """
        try:
            # Check if text contains SSML tags
            if not re.search(r'<[^>]+>', text):
                return text, {}
            
            # Extract plain text by removing tags (simple regex-based)
            plain_text = re.sub(r'<[^>]+>', '', text)
            
            # Extract SSML attributes (basic implementation)
            ssml_attributes = {}
            
            # Extract prosody attributes
            prosody_match = re.search(r'<prosody[^>]*rate="([^"]*)"', text)
            if prosody_match:
                ssml_attributes['rate'] = prosody_match.group(1)
            
            prosody_match = re.search(r'<prosody[^>]*pitch="([^"]*)"', text)
            if prosody_match:
                ssml_attributes['pitch'] = prosody_match.group(1)
            
            prosody_match = re.search(r'<prosody[^>]*volume="([^"]*)"', text)
            if prosody_match:
                ssml_attributes['volume'] = prosody_match.group(1)
            
            return plain_text, ssml_attributes
            
        except Exception as e:
            logger.error(f"SSML parsing failed: {e}")
            # Return original text if parsing fails
            return text, {}
    
    def validate_text(self, text: str) -> bool:
        """Validate text input for TTS processing."""
        try:
            # Check text is not empty
            if not text or not text.strip():
                raise InvalidTextError("Text cannot be empty")
            
            # Check text length is reasonable
            if len(text) > 5000:
                raise InvalidTextError("Text cannot exceed 5000 characters")
            
            # Check text doesn't contain only special characters
            if not re.search(r'[a-zA-Z\u0900-\u097F\u0A80-\u0AFF\u0B00-\u0B7F\u0B80-\u0BFF\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F\u0D80-\u0DFF\u0E00-\u0E7F\u0E80-\u0EFF\u0F00-\u0FFF]', text):
                raise InvalidTextError("Text must contain at least some alphabetic characters")
            
            return True
            
        except InvalidTextError:
            raise
        except Exception as e:
            logger.error(f"Text validation failed: {e}")
            raise InvalidTextError(f"Text validation failed: {e}")
    
    def normalize_text(self, text: str, language: str = "en") -> str:
        """Normalize text for TTS processing."""
        try:
            # Remove control characters (except newline, tab)
            text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
            
            # Remove zero-width characters
            text = re.sub(r'[\u200B-\u200D\uFEFF]', '', text)
            
            # Normalize Unicode (NFC normalization)
            text = unicodedata.normalize('NFC', text)
            
            # Language-specific normalization
            if language in ["hi", "bn", "gu", "mr", "pa", "or", "as"]:
                # For Devanagari and related scripts
                text = re.sub(r'[।]+', '.', text)  # Replace multiple dandas with single period
                text = re.sub(r'[॥]+', '..', text)  # Replace double dandas with double period
            
            # Normalize whitespace
            text = re.sub(r'\s+', ' ', text)
            text = text.strip()
            
            return text
            
        except Exception as e:
            logger.error(f"Text normalization failed: {e}")
            raise TextProcessingError(f"Text normalization failed: {e}")
    
    def estimate_audio_duration(self, text: str, language: str = "en", speaking_rate: float = 150.0) -> float:
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
