"""
TextBase — base class for all text-backed inference services.

Item presence (each item needs a 'source') is declared via REQUIRED_ITEM_FIELDS
and checked by the generic BaseTaskService.validate_request. Config/language
rules live in validate_config:
  - config block present
  - sourceLanguage when a language block is given
  - targetLanguage + not-equal (REQUIRES_TARGET_LANGUAGE=True)
"""

from typing import Any, Dict, Optional
from services.base.task_service import BaseTaskService
from utils import text_utils


class TextBase(BaseTaskService):
    payload_key = "input"  # text input list lives under payload['input']

    # Each text item must carry a non-empty 'source'.
    REQUIRED_ITEM_FIELDS = (("source",),)

    # Set True in subclasses that require both source and target language (NMT, Transliteration)
    REQUIRES_TARGET_LANGUAGE: bool = False

    # ------------------------------------------------------------------
    # Common language helpers
    # ------------------------------------------------------------------

    def _get_language(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return payload.get("config", {}).get("language", {})

    def _extract_source_lang(self, language: Dict[str, Any]) -> Optional[str]:
        return language.get("sourceLanguage")

    def _extract_target_lang(self, language: Dict[str, Any]) -> Optional[str]:
        return language.get("targetLanguage")

    # ------------------------------------------------------------------
    # Config / language validation (cross-field; item presence is generic)
    # ------------------------------------------------------------------

    async def validate_config(self, payload: Dict[str, Any]) -> None:
        if not payload.get("config"):
            raise ValueError(f"{self.task_name}: payload must contain a 'config' field")

        language = self._get_language(payload)
        # Services that require a target language (NMT, Transliteration) need the
        # language block. Other text services (e.g. language detection) leave it
        # optional, validating sourceLanguage only when a block is supplied.
        if self.REQUIRES_TARGET_LANGUAGE:
            source_lang = self._extract_source_lang(language)
            target_lang = self._extract_target_lang(language)
            if not source_lang:
                raise ValueError(f"{self.task_name}: config.language.sourceLanguage is required")
            if not target_lang:
                raise ValueError(f"{self.task_name}: config.language.targetLanguage is required")
            if source_lang == target_lang:
                raise ValueError(f"{self.task_name}: sourceLanguage and targetLanguage cannot be the same")
        elif language and not self._extract_source_lang(language):
            raise ValueError(f"{self.task_name}: config.language.sourceLanguage is required")

    # ------------------------------------------------------------------
    # preprocess_input
    # ------------------------------------------------------------------

    async def preprocess_input(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        input_data = payload.get(self.payload_key) or []
        source_texts = self.extract_field_from_items(input_data, "source")
        sanitized = [text_utils.sanitize_source(t) for t in source_texts]

        items = [
            {**item, "source": sanitized[idx] if idx < len(sanitized) else ""}
            for idx, item in enumerate(input_data)
        ]

        payload[self.payload_key] = items
        return payload
