"""
Language Detection Service
Service for automatic language detection using Unicode script analysis.
"""

import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class LanguageDetectionService:
    """Service for automatic language detection using Unicode script analysis."""

    SCRIPT_RANGES = {
        "Deva": (0x0900, 0x097F),
        "Arab": (0x0600, 0x06FF),
        "Taml": (0x0B80, 0x0BFF),
        "Telu": (0x0C00, 0x0C7F),
        "Knda": (0x0C80, 0x0CFF),
        "Mlym": (0x0D00, 0x0D7F),
        "Beng": (0x0980, 0x09FF),
        "Gujr": (0x0A80, 0x0AFF),
        "Guru": (0x0A00, 0x0A7F),
        "Orya": (0x0B00, 0x0B7F),
        "Latn": (0x0000, 0x007F),
    }

    SCRIPT_TO_LANGUAGE = {
        "Deva": "hi",
        "Arab": "ur",
        "Taml": "ta",
        "Telu": "te",
        "Knda": "kn",
        "Mlym": "ml",
        "Beng": "bn",
        "Gujr": "gu",
        "Guru": "pa",
        "Orya": "or",
        "Latn": "en",
    }

    def __init__(self, confidence_threshold: float = 0.7):
        self.confidence_threshold = confidence_threshold

    def detect_language(self, text: str) -> str:
        if not text or not text.strip():
            return "en"
        detected_script = self.detect_script(text)
        return self.SCRIPT_TO_LANGUAGE.get(detected_script, "en")

    def detect_script(self, text: str) -> str:
        if not text or not text.strip():
            return "Latn"
        script_counts = {}
        total_chars = 0
        for char in text:
            if char.isspace():
                continue
            total_chars += 1
            char_code = ord(char)
            for script, (start, end) in self.SCRIPT_RANGES.items():
                if start <= char_code <= end:
                    script_counts[script] = script_counts.get(script, 0) + 1
                    break
        if not script_counts:
            return "Latn"
        return max(script_counts.items(), key=lambda x: x[1])[0]

    def calculate_confidence(self, text: str, detected_lang: str) -> float:
        if not text or not text.strip():
            return 0.0
        detected_script = None
        for script, lang in self.SCRIPT_TO_LANGUAGE.items():
            if lang == detected_lang:
                detected_script = script
                break
        if not detected_script:
            return 0.0
        script_start, script_end = self.SCRIPT_RANGES[detected_script]
        script_chars = 0
        total_chars = 0
        for char in text:
            if char.isspace():
                continue
            total_chars += 1
            if script_start <= ord(char) <= script_end:
                script_chars += 1
        if total_chars == 0:
            return 0.0
        script_ratio = script_chars / total_chars
        length_factor = min(1.0, len(text.strip()) / 50.0)
        script_diversity = len(set(self._get_char_script(char) for char in text if not char.isspace()))
        diversity_factor = 1.0 / script_diversity if script_diversity > 0 else 1.0
        return min(1.0, max(0.0, script_ratio * length_factor * diversity_factor))

    def _get_char_script(self, char: str) -> str:
        char_code = ord(char)
        for script, (start, end) in self.SCRIPT_RANGES.items():
            if start <= char_code <= end:
                return script
        return "Latn"

    def detect_with_confidence(self, text: str) -> Tuple[str, float]:
        detected_lang = self.detect_language(text)
        confidence = self.calculate_confidence(text, detected_lang)
        return detected_lang, confidence

    def is_confidence_sufficient(self, confidence: float) -> bool:
        return confidence >= self.confidence_threshold
