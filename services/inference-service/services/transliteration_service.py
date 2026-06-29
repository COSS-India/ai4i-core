"""Transliteration TaskService."""
from typing import Any, Dict

from services.base.text_base import TranslationTextBase


class TransliterationTaskService(TranslationTextBase):
    async def validate_request(self, payload: Dict[str, Any]) -> None:
        """Translation rules (super) plus the transliteration-specific
        numSuggestions/isSentence rule. Also derives is_word_level for the
        input mapper."""
        await super().validate_request(payload)

        config = payload.get("config", {})
        num_suggestions = config.get("numSuggestions") or 0
        is_sentence = config.get("isSentence") or False

        if num_suggestions > 0 and is_sentence:
            raise ValueError(
                "Transliteration: numSuggestions is not valid for sentence-level transliteration"
            )

        # is_word_level = not isSentence: a boolean inversion the typed input
        # path cannot express, injected for the input mapper (request.config.is_word_level).
        # top_k is a plain rename, handled in config (TOP_K reads numSuggestions).
        config["is_word_level"] = not is_sentence

    # output: adapter_config-driven (pair_with_input "input.source", include_config
    # false). Top-k suggestions arrive as extra Triton batch items, pairing with
    # "" once inputs run out — matching the contract.


__all__ = ["TransliterationTaskService"]
