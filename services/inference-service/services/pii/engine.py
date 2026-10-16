"""Presidio engine singleton — loads both spaCy models once at startup."""

import logging
from typing import Dict, List, Optional, Set, Tuple

from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_analyzer.predefined_recognizers import SpacyRecognizer
from presidio_analyzer.predefined_recognizers.country_specific.india import (
    InAadhaarRecognizer,
    InGstinRecognizer,
    InPanRecognizer,
    InPassportRecognizer,
    InVehicleRegistrationRecognizer,
    InVoterRecognizer,
)
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import EngineResult, OperatorConfig

from config import settings
from services.pii.model_registry import get_spacy_lang_code
from services.pii.operators import OPERATOR_NAME, InstanceCounterAnonymizer

logger = logging.getLogger(__name__)

_engine: Optional["PresidioEngine"] = None

# Languages xx_ent_wiki_sm's NER was trained on (WikiNER). For any other
# non-English language it finds almost no names, places or organisations.
MULTILINGUAL_NER_LANGUAGES = {"de", "es", "fr", "it", "nl", "pl", "pt", "ru"}

# Entity name prefixes that belong to a specific country.  Any entity whose
# name starts with one of these prefixes is considered country-specific and
# will be excluded when a different country is requested.
COUNTRY_ENTITY_PREFIXES: Dict[str, str] = {
    "IN": "IN_",
    "US": "US_",
    "UK": "UK_",
}


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
        for recognizer in [
            InAadhaarRecognizer(),
            InGstinRecognizer(),
            InPanRecognizer(),
            InPassportRecognizer(),
            InVehicleRegistrationRecognizer(),
            InVoterRecognizer(),
        ]:
            self._analyzer.registry.add_recognizer(recognizer)
        self._anonymizer = AnonymizerEngine()
        # Older presidio-anonymizer (e.g. the pinned 2.2.35) has no add_anonymizer;
        # it discovers Operator subclasses automatically, so the import is enough.
        if hasattr(self._anonymizer, "add_anonymizer"):
            self._anonymizer.add_anonymizer(InstanceCounterAnonymizer)
        logger.info(
            "Presidio engine loaded (en_model=%s, multilingual_model=%s)",
            settings.PII_SPACY_EN_MODEL,
            settings.PII_SPACY_MULTILINGUAL_MODEL,
        )

    def analyze(
        self,
        text: str,
        source_language: str,
        entities: Optional[List[str]] = None,
    ) -> List[RecognizerResult]:
        """Detect PII. entities=None means every supported entity."""
        return self._analyzer.analyze(
            text=text,
            language=get_spacy_lang_code(source_language),
            entities=entities,
        )

    def detectable_entities(self, source_language: str, country: Optional[str] = None) -> Set[str]:
        """Entities Presidio can detect in text of this language.

        Asking for any other entity raises "No matching recognizers" (or
        silently finds nothing). Entities served only by spaCy NER (PERSON,
        LOCATION, ...) are left out where the loaded model has no NER for the
        language.

        When country is given (e.g. "IN", "US"), only universal entities and
        entities belonging to that country are returned.
        """
        recognizers = self._analyzer.registry.get_recognizers(
            language=get_spacy_lang_code(source_language), all_fields=True
        )
        ner_works = source_language == "en" or source_language in MULTILINGUAL_NER_LANGUAGES
        all_entities = {
            entity
            for recognizer in recognizers
            if ner_works or not isinstance(recognizer, SpacyRecognizer)
            for entity in recognizer.supported_entities
        }
        if country is None:
            return all_entities
        country_upper = country.upper()
        selected_prefix = COUNTRY_ENTITY_PREFIXES.get(country_upper)
        all_prefixes = set(COUNTRY_ENTITY_PREFIXES.values())
        return {
            entity for entity in all_entities
            if not any(entity.startswith(p) for p in all_prefixes)
            or (selected_prefix is not None and entity.startswith(selected_prefix))
        }

    def anonymize(
        self,
        text: str,
        analyzer_results: List[RecognizerResult],
        entity_mapping: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> Tuple[EngineResult, Dict[str, Dict[str, str]]]:
        """Replace each entity with a numbered token (<PERSON_1>, ...).

        Pass a shared entity_mapping across multiple calls to keep counters
        consistent (e.g. across all messages in a single request).

        Returns Presidio's EngineResult and the {entity_type: {value: token}}
        map the operator filled in. The map holds raw PII; never log it.
        """
        if entity_mapping is None:
            entity_mapping = {}
        result = self._anonymizer.anonymize(
            text=text,
            analyzer_results=analyzer_results,
            operators={"DEFAULT": OperatorConfig(OPERATOR_NAME, {"entity_mapping": entity_mapping})},
        )
        return result, entity_mapping


def get_engine() -> PresidioEngine:
    global _engine
    if _engine is None:
        _engine = PresidioEngine()
    return _engine
