"""Transliteration TaskService."""
from typing import Any, Dict, Optional

from services.base.text_base import TextBase

_SMALL_THRESHOLD = 200
_MEDIUM_THRESHOLD = 1000


class TransliterationTaskService(TextBase):
    REQUIRES_TARGET_LANGUAGE = True  # enables target_language + not-equal check in base

    async def process(
        self,
        payload: Dict[str, Any],
        serviceInfo: Optional[Dict[str, Any]] = None,
    ) -> Any:
        return self._stub_response(payload)

    def _stub_response(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        from response_test.responses.transliteration_responses import (
            SMALL_TRANSLITERATION_RESPONSE,
            MEDIUM_TRANSLITERATION_RESPONSE,
            LARGE_TRANSLITERATION_RESPONSE,
        )
        input_items = payload.get("input") or []
        total_length = sum(len(item.get("source", "")) for item in input_items)
        if total_length < _SMALL_THRESHOLD:
            return SMALL_TRANSLITERATION_RESPONSE
        if total_length < _MEDIUM_THRESHOLD:
            return MEDIUM_TRANSLITERATION_RESPONSE
        return LARGE_TRANSLITERATION_RESPONSE

    async def validate_request(self, payload):
        await super().validate_request(payload)  # handles input + source/target language checks

        # --- Transliteration-specific: numSuggestions/isSentence + derived field injection ---
        config = payload.get("config", {})
        num_suggestions = config.get("num_suggestions") or config.get("numSuggestions") or 0
        is_sentence = config.get("is_sentence") or config.get("isSentence") or False

        if num_suggestions > 0 and is_sentence:
            raise ValueError("Transliteration: numSuggestions is not valid for sentence-level transliteration")

        # Inject derived fields so mapper can resolve value_path: request.config.is_word_level/top_k
        config["is_word_level"] = not is_sentence
        config["top_k"] = num_suggestions

        src = self._extract_source_lang(self._get_language(payload))
        tgt = self._extract_target_lang(self._get_language(payload))
        self.logger.info(f"Transliteration: {src} -> {tgt} (sentence={is_sentence}, top_k={num_suggestions}, {len(payload.get('input', []))} inputs)")

    # postprocess_output: adapter_config-driven (pair_with_input "input.source"
    # + include_config false). Top-k suggestions arrive as extra Triton batch
    # items, which pair with "" once inputs run out — matching the contract.

__all__ = ["TransliterationTaskService"]
