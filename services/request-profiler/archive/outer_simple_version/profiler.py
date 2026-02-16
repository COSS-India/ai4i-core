"""RequestProfiler - Core profiling logic for Indian language requests"""

import re
import time
from typing import Dict, List, Tuple
from .config import settings
from .schemas import LanguageDetection, RequestProfile, IntentType


class RequestProfiler:
    """Main profiler class for analyzing Indian language requests"""
    
    def __init__(self):
        self.languages = settings.LANGUAGES
        self.language_names = settings.LANGUAGE_NAMES
        
        # Complexity markers by language
        self.complexity_markers = {
            "hi": ["संविधान", "विज्ञान", "प्रौद्योगिकी", "गणित"],
            "bn": ["সংবিধান", "বিজ্ঞান", "প্রযুক্তি", "গণিত"],
            "ta": ["அரசியலமைப்பு", "அறிவியல்", "தொழில்நுட்பம்", "கணிதம்"],
            "te": ["సంవిధానం", "శాస్త్రం", "సాంకేతికత", "గణితం"],
            "kn": ["ಸಂವಿಧಾನ", "ವಿಜ್ಞಾನ", "ತಂತ್ರಜ್ಞಾನ", "ಗಣಿತ"],
            "as": ["সংবিধান", "বিজ্ঞান", "প্রযুক্তি", "গণিত"]
        }
        
        # Intent keywords
        self.intent_keywords = {
            IntentType.TECHNICAL: ["code", "error", "bug", "api", "function", "class"],
            IntentType.LEGAL: ["contract", "law", "agreement", "terms", "policy"],
            IntentType.MEDICAL: ["symptom", "diagnosis", "treatment", "medicine", "health"],
            IntentType.CREATIVE: ["story", "poem", "song", "write", "creative"],
            IntentType.GENERAL: []
        }
    
    def detect_language(self, text: str) -> LanguageDetection:
        """Detect the language of the given text"""
        # Simple character-based detection for Indian languages
        text_lower = text.lower()
        
        # Language-specific character ranges
        language_chars = {
            "hi": "अआइईउऊऋएऐओऔकखगघचछजझटठडढणतथदधनपफबभमयरलवशषसह",
            "bn": "অআইঈউঊঋএঐওঔকখগঘচছজঝঞটঠডঢণতথদধনপফবভমযরলশষসহ",
            "ta": "அஆஇஈஉஊஎஏஐஒஓஔகஙசஜஞடணதநபமவயரறலளழவ",
            "te": "అఆఇఈఉఊఋఎఏఐఒఓఔకఖగఘఙచఛజఝఞటఠడఢణతథదధనపఫబభమయరలవశషసహ",
            "kn": "ಅಆಇಈಉಊಋಎಏಐಒಓಔಕಖಗಘಙಚಛಜಝಞಟಠಡಢಣತಥದಧನಪಫಬಭಮಯರಲವಶಷಸಹ",
            "as": "অআইঈউঊঋএঐওঔকখগঘচছজঝঞটঠডঢণতথদধনপফবভমযরলশষসহ"
        }
        
        # Count characters from each language
        scores = {}
        for lang, chars in language_chars.items():
            count = sum(1 for char in text if char in chars)
            scores[lang] = count
        
        # Find best match
        best_lang = max(scores, key=scores.get)
        total_chars = sum(scores.values())
        
        if total_chars == 0:
            confidence = 0.0
        else:
            confidence = scores[best_lang] / total_chars
        
        return LanguageDetection(
            language=best_lang,
            language_name=self.language_names.get(best_lang, "Unknown"),
            confidence=confidence
        )
    
    def calculate_complexity(self, text: str, language: str) -> float:
        """Calculate complexity score (1-10)"""
        words = text.split()
        word_count = len(words)
        sentence_count = len(re.split(r'[.!?]', text))
        
        # Base complexity from length
        length_score = min(10, word_count / 10)
        
        # Add complexity markers
        marker_bonus = 0
        if language in self.complexity_markers:
            markers = self.complexity_markers[language]
            for marker in markers:
                if marker in text:
                    marker_bonus += 1
        
        # Average sentence length
        avg_sentence_len = word_count / max(1, sentence_count)
        sentence_bonus = min(2, avg_sentence_len / 10)
        
        final_score = min(10, length_score + marker_bonus + sentence_bonus)
        return round(final_score, 1)
    
    def classify_intent(self, text: str) -> IntentType:
        """Classify the intent of the request"""
        text_lower = text.lower()
        
        scores = {intent: 0 for intent in IntentType}
        
        for intent, keywords in self.intent_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    scores[intent] += 1
        
        # Return highest scoring intent
        best_intent = max(scores, key=scores.get)
        return best_intent if scores[best_intent] > 0 else IntentType.GENERAL
    
    def suggest_model(self, complexity: float, intent: IntentType) -> str:
        """Suggest appropriate model based on profile"""
        if complexity < 3:
            return "small"
        elif complexity < 6:
            return "medium"
        else:
            return "large"
    
    def profile(self, text: str) -> RequestProfile:
        """Profile a single request"""
        start_time = time.time()
        
        language = self.detect_language(text)
        complexity = self.calculate_complexity(text, language.language)
        intent = self.classify_intent(text)
        suggested_model = self.suggest_model(complexity, intent)
        
        processing_time = (time.time() - start_time) * 1000
        
        return RequestProfile(
            text=text,
            language=language,
            complexity_score=complexity,
            intent=intent,
            suggested_model=suggested_model,
            processing_time_ms=round(processing_time, 2)
        )
    
    def batch_profile(self, texts: List[str]) -> List[RequestProfile]:
        """Profile multiple requests"""
        return [self.profile(text) for text in texts]
    
    def get_supported_languages(self) -> List[Dict]:
        """Get list of supported languages"""
        return [
            {"code": lang, "name": self.language_names.get(lang, lang)}
            for lang in self.languages
        ]
