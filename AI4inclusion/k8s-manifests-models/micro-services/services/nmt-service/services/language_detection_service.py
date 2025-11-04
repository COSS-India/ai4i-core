"""
Language Detection Service
Service for automatic language detection using Unicode script analysis
"""

import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class LanguageDetectionService:
    """Service for automatic language detection using Unicode script analysis."""
    
    # Unicode ranges for different scripts
    SCRIPT_RANGES = {
        "Deva": (0x0900, 0x097F),  # Devanagari
        "Arab": (0x0600, 0x06FF),  # Arabic
        "Taml": (0x0B80, 0x0BFF),  # Tamil
        "Telu": (0x0C00, 0x0C7F),  # Telugu
        "Knda": (0x0C80, 0x0CFF),  # Kannada
        "Mlym": (0x0D00, 0x0D7F),  # Malayalam
        "Beng": (0x0980, 0x09FF),  # Bengali
        "Gujr": (0x0A80, 0x0AFF),  # Gujarati
        "Guru": (0x0A00, 0x0A7F),  # Gurmukhi (Punjabi)
        "Orya": (0x0B00, 0x0B7F),  # Oriya
        "Latn": (0x0000, 0x007F),  # Latin (Basic ASCII)
    }
    
    # Language code mapping
    SCRIPT_TO_LANGUAGE = {
        "Deva": "hi",  # Hindi
        "Arab": "ur",  # Urdu
        "Taml": "ta",  # Tamil
        "Telu": "te",  # Telugu
        "Knda": "kn",  # Kannada
        "Mlym": "ml",  # Malayalam
        "Beng": "bn",  # Bengali
        "Gujr": "gu",  # Gujarati
        "Guru": "pa",  # Punjabi
        "Orya": "or",  # Oriya
        "Latn": "en",  # English
    }
    
    def __init__(self, confidence_threshold: float = 0.7):
        """Initialize language detection service.
        
        Args:
            confidence_threshold: Minimum confidence score for language detection
        """
        self.confidence_threshold = confidence_threshold
    
    def detect_language(self, text: str) -> str:
        """Detect language from text using Unicode script analysis.
        
        Args:
            text: Input text to analyze
            
        Returns:
            Detected language code (e.g., 'hi', 'en', 'ta')
        """
        if not text or not text.strip():
            return "en"  # Default to English for empty text
        
        detected_script = self.detect_script(text)
        return self.SCRIPT_TO_LANGUAGE.get(detected_script, "en")
    
    def detect_script(self, text: str) -> str:
        """Detect script from text using Unicode ranges.
        
        Args:
            text: Input text to analyze
            
        Returns:
            Detected script code (e.g., 'Deva', 'Arab', 'Latn')
        """
        if not text or not text.strip():
            return "Latn"  # Default to Latin for empty text
        
        script_counts = {}
        total_chars = 0
        
        for char in text:
            if char.isspace():
                continue  # Skip whitespace
                
            total_chars += 1
            char_code = ord(char)
            
            for script, (start, end) in self.SCRIPT_RANGES.items():
                if start <= char_code <= end:
                    script_counts[script] = script_counts.get(script, 0) + 1
                    break
        
        if not script_counts:
            return "Latn"  # Default to Latin if no script detected
        
        # Return the script with the highest count
        detected_script = max(script_counts.items(), key=lambda x: x[1])[0]
        return detected_script
    
    def calculate_confidence(self, text: str, detected_lang: str) -> float:
        """Calculate confidence score for language detection.
        
        Args:
            text: Input text that was analyzed
            detected_lang: Detected language code
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        if not text or not text.strip():
            return 0.0
        
        # Get the script for the detected language
        detected_script = None
        for script, lang in self.SCRIPT_TO_LANGUAGE.items():
            if lang == detected_lang:
                detected_script = script
                break
        
        if not detected_script:
            return 0.0
        
        # Count characters in the detected script
        script_start, script_end = self.SCRIPT_RANGES[detected_script]
        script_chars = 0
        total_chars = 0
        
        for char in text:
            if char.isspace():
                continue  # Skip whitespace
                
            total_chars += 1
            char_code = ord(char)
            
            if script_start <= char_code <= script_end:
                script_chars += 1
        
        if total_chars == 0:
            return 0.0
        
        # Base confidence on percentage of characters in detected script
        script_ratio = script_chars / total_chars
        
        # Adjust confidence based on text length (longer text = higher confidence)
        length_factor = min(1.0, len(text.strip()) / 50.0)  # Normalize to 50 chars
        
        # Penalize mixed scripts (reduce confidence if multiple scripts detected)
        script_diversity = len(set(
            self._get_char_script(char) for char in text if not char.isspace()
        ))
        diversity_factor = 1.0 / script_diversity if script_diversity > 0 else 1.0
        
        # Calculate final confidence
        confidence = script_ratio * length_factor * diversity_factor
        
        return min(1.0, max(0.0, confidence))
    
    def _get_char_script(self, char: str) -> str:
        """Get script for a single character."""
        char_code = ord(char)
        
        for script, (start, end) in self.SCRIPT_RANGES.items():
            if start <= char_code <= end:
                return script
        
        return "Latn"  # Default to Latin
    
    def detect_with_confidence(self, text: str) -> Tuple[str, float]:
        """Detect language and return confidence score.
        
        Args:
            text: Input text to analyze
            
        Returns:
            Tuple of (detected_language, confidence_score)
        """
        detected_lang = self.detect_language(text)
        confidence = self.calculate_confidence(text, detected_lang)
        
        return detected_lang, confidence
    
    def is_confidence_sufficient(self, confidence: float) -> bool:
        """Check if confidence score meets the threshold.
        
        Args:
            confidence: Confidence score to check
            
        Returns:
            True if confidence meets threshold, False otherwise
        """
        return confidence >= self.confidence_threshold
