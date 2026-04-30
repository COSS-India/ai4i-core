"""
Text Service
Text processing utilities for NMT.
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

    def normalize_text(self, text: str) -> str:
        try:
            text = text.replace("\n", " ")
            text = text.strip()
            text = re.sub(r'\s+', ' ', text)
            return text
        except Exception as e:
            logger.error(f"Failed to normalize text: {e}")
            raise InvalidTextError(f"Failed to normalize text: {e}")

    def validate_text_length(self, text: str, max_length: int = 10000) -> bool:
        if len(text) > max_length:
            raise TextTooLongError(f"Text length {len(text)} exceeds maximum {max_length}")
        return True

    def detect_language(self, text: str) -> str:
        try:
            if any('\u0900' <= char <= '\u097F' for char in text):
                return "hi"
            if any('\u0B80' <= char <= '\u0BFF' for char in text):
                return "ta"
            if any('\u0C00' <= char <= '\u0C7F' for char in text):
                return "te"
            if any('\u0C80' <= char <= '\u0CFF' for char in text):
                return "kn"
            if any('\u0D00' <= char <= '\u0D7F' for char in text):
                return "ml"
            if any('\u0980' <= char <= '\u09FF' for char in text):
                return "bn"
            if any('\u0A80' <= char <= '\u0AFF' for char in text):
                return "gu"
            if any('\u0600' <= char <= '\u06FF' for char in text):
                return "ur"
            return "en"
        except Exception as e:
            logger.error(f"Failed to detect language: {e}")
            return "en"

    def sanitize_text(self, text: str) -> str:
        try:
            text = ''.join(char for char in text if unicodedata.category(char)[0] != 'C' or char in '\n\t')
            text = re.sub(r'[\u200b-\u200d\ufeff]', '', text)
            text = unicodedata.normalize('NFC', text)
            return text
        except Exception as e:
            logger.error(f"Failed to sanitize text: {e}")
            raise InvalidTextError(f"Failed to sanitize text: {e}")

    def split_long_text(self, text: str, max_length: int = 5000) -> List[str]:
        try:
            if len(text) <= max_length:
                return [text]
            sentences = re.split(r'[.!?\u0964]', text)
            chunks = []
            current_chunk = ""
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                if sentence and not sentence.endswith(('.', '!', '?', '\u0964')):
                    sentence += '.'
                if len(current_chunk) + len(sentence) + 1 <= max_length:
                    current_chunk = current_chunk + " " + sentence if current_chunk else sentence
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = sentence
            if current_chunk:
                chunks.append(current_chunk)
            return chunks if chunks else [text]
        except Exception as e:
            logger.error(f"Failed to split text: {e}")
            return [text]
