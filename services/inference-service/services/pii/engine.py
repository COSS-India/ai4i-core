"""Presidio engine singleton — loads both spaCy models once at startup."""

import logging
from typing import List, Optional

from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine

from config import settings
from services.pii.model_registry import get_spacy_lang_code

logger = logging.getLogger(__name__)

_engine: Optional["PresidioEngine"] = None


class PresidioEngine:
    def __init__(self) -> None:
        nlp_configuration = {
            "nlp_engine_name": "spacy",
            "models": [
                {"lang_code": "en", "model_name": settings.PII_SPACY_EN_MODEL},
                {"lang_code": "xx", "model_name": settings.PII_SPACY_MULTILINGUAL_MODEL},
            ],
        }
        nlp_engine = NlpEngineProvider(nlp_configuration=nlp_configuration).create_engine()
        self._analyzer = AnalyzerEngine(
            nlp_engine=nlp_engine,
            supported_languages=["en", "xx"],
        )
        self._anonymizer = AnonymizerEngine()
        logger.info(
            "Presidio engine loaded (en_model=%s, multilingual_model=%s)",
            settings.PII_SPACY_EN_MODEL,
            settings.PII_SPACY_MULTILINGUAL_MODEL,
        )

    def analyze(self, text: str, source_language: str) -> List[RecognizerResult]:
        lang_code = get_spacy_lang_code(source_language)
        return self._analyzer.analyze(text=text, language=lang_code)

    def anonymize(self, text: str, analyzer_results: List[RecognizerResult]) -> str:
        return self._anonymizer.anonymize(text=text, analyzer_results=analyzer_results).text


def get_engine() -> PresidioEngine:
    global _engine
    if _engine is None:
        _engine = PresidioEngine()
    return _engine
