"""
TextBase — base class for all text-backed inference services.

Centralised validation:
  - input existence and non-empty
  - source_language (all services with language config)
  - target_language + not-equal (REQUIRES_TARGET_LANGUAGE=True)

Child classes only add service-specific logic on top of super().validate_request().
"""

from typing import Any, Dict, List, Optional
from services.base.task_service import BaseTaskService
from utils import text_utils


class TextBase(BaseTaskService):
    payload_key = "input"  # text input list lives under payload['input']

    # Set True in subclasses that require both source and target language (NMT, Transliteration)
    REQUIRES_TARGET_LANGUAGE: bool = False

    # ------------------------------------------------------------------
    # Common language helpers
    # ------------------------------------------------------------------

    def _get_language(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return payload.get("config", {}).get("language", {})

    def _extract_source_lang(self, language: Dict[str, Any]) -> Optional[str]:
        return language.get("source_language") or language.get("sourceLanguage")

    def _extract_target_lang(self, language: Dict[str, Any]) -> Optional[str]:
        return language.get("target_language") or language.get("targetLanguage")

    # ------------------------------------------------------------------
    # Common validate_request
    # ------------------------------------------------------------------

    async def validate_request(self, payload: Any) -> None:
        await super().validate_request(payload)

        if not payload.get("input"):
            raise ValueError(f"{self.task_name}: payload must contain a non-empty 'input' field")
        if not payload.get("config"):
            raise ValueError(f"{self.task_name}: payload must contain a 'config' field")

        for idx, item in enumerate(payload.get("input", [])):
            source = item.get("source")
            if not source or not isinstance(source, str):
                raise ValueError(f"{self.task_name}: input[{idx}]['source'] must be a non-empty string")

        language = self._get_language(payload)
        if language:
            source_lang = self._extract_source_lang(language)
            if not source_lang:
                raise ValueError(f"{self.task_name}: config.language.source_language is required")

            if self.REQUIRES_TARGET_LANGUAGE:
                target_lang = self._extract_target_lang(language)
                if not target_lang:
                    raise ValueError(f"{self.task_name}: config.language.target_language is required")
                if source_lang == target_lang:
                    raise ValueError(f"{self.task_name}: source_language and target_language cannot be the same")

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

    # ------------------------------------------------------------------
    # Text helpers
    # ------------------------------------------------------------------

    def _pair_with_sources(
        self,
        response_items: List[Dict[str, Any]],
        source_texts: List[str],
    ) -> List[Dict[str, Any]]:
        paired = []
        for idx, item in enumerate(response_items):
            source = source_texts[idx] if idx < len(source_texts) else ""
            paired.append({**item, "source": source})
        return paired
