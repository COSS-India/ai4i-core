"""
Text processing service with utilities for text manipulation and SSML support.
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
        """Process TTS input text for normalization."""
        try:
            processed_text = text.replace("\u0964", ".")
            processed_text = processed_text.strip()
            processed_text = re.sub(r"\s+", " ", processed_text)
            return processed_text
        except Exception as e:
            logger.error(f"Text processing failed: {e}")
            raise TextProcessingError(f"Failed to process text: {e}")

    def chunk_text(self, text: str, max_length: int = 400) -> List[str]:
        """Split long text into smaller chunks for TTS processing."""
        try:
            if len(text) <= max_length:
                return [text]

            words = text.split(" ")
            chunks = []
            tmp_sent = ""

            for word in words:
                if len(tmp_sent) + len(word) + 1 <= max_length:
                    if tmp_sent:
                        tmp_sent += " " + word
                    else:
                        tmp_sent = word
                else:
                    if tmp_sent:
                        chunks.append(tmp_sent)
                    tmp_sent = word

            if tmp_sent:
                chunks.append(tmp_sent)

            return chunks
        except Exception as e:
            logger.error(f"Text chunking failed: {e}")
            raise TextProcessingError(f"Failed to chunk text: {e}")

    def parse_ssml(self, text: str) -> Tuple[str, Dict[str, Any]]:
        """Parse SSML tags and extract attributes."""
        try:
            if not re.search(r"<[^>]+>", text):
                return text, {}

            plain_text = re.sub(r"<[^>]+>", "", text)
            ssml_attributes = {}

            prosody_match = re.search(r'<prosody[^>]*rate="([^"]*)"', text)
            if prosody_match:
                ssml_attributes["rate"] = prosody_match.group(1)

            prosody_match = re.search(r'<prosody[^>]*pitch="([^"]*)"', text)
            if prosody_match:
                ssml_attributes["pitch"] = prosody_match.group(1)

            prosody_match = re.search(r'<prosody[^>]*volume="([^"]*)"', text)
            if prosody_match:
                ssml_attributes["volume"] = prosody_match.group(1)

            return plain_text, ssml_attributes
        except Exception as e:
            logger.error(f"SSML parsing failed: {e}")
            return text, {}

    def validate_text(self, text: str) -> bool:
        """Validate text input for TTS processing."""
        try:
            if not text or not text.strip():
                raise InvalidTextError("Text cannot be empty")

            if len(text) > 5000:
                raise InvalidTextError("Text cannot exceed 5000 characters")

            has_letter = False
            for char in text:
                if unicodedata.category(char).startswith("L"):
                    has_letter = True
                    break

            if not has_letter:
                raise InvalidTextError("Text must contain at least one letter character")

            return True
        except InvalidTextError:
            raise
        except Exception as e:
            logger.error(f"Text validation failed: {e}")
            raise InvalidTextError(f"Text validation failed: {e}")

    def normalize_text(self, text: str, language: str = "en") -> str:
        """Normalize text for TTS processing."""
        try:
            text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
            text = re.sub(r"[\u200B-\u200D\uFEFF]", "", text)
            text = unicodedata.normalize("NFC", text)

            if language in ["hi", "bn", "gu", "mr", "pa", "or", "as"]:
                text = re.sub(r"[\u0964]+", ".", text)
                text = re.sub(r"[\u0965]+", "..", text)

            text = re.sub(r"\s+", " ", text)
            text = text.strip()
            return text
        except Exception as e:
            logger.error(f"Text normalization failed: {e}")
            raise TextProcessingError(f"Text normalization failed: {e}")

    def estimate_audio_duration(self, text: str, language: str = "en", speaking_rate: float = 150.0) -> float:
        """Estimate audio duration for given text."""
        try:
            word_count = len(text.split())
            duration = (word_count / speaking_rate) * 60
            duration *= 1.2
            return duration
        except Exception as e:
            logger.error(f"Duration estimation failed: {e}")
            return 0.0
