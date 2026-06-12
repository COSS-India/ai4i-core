"""Transliteration TaskService."""
from typing import Any, Dict

from services.base.text_base import TextBase


class TransliterationTaskService(TextBase):
    REQUIRES_TARGET_LANGUAGE = True  # source/target language checks via TextBase

    async def validate_config(self, payload: Dict[str, Any]) -> None:
        await super().validate_config(payload)  # config present + language rules

        config = payload.get("config", {})
        num_suggestions = config.get("numSuggestions") or 0
        is_sentence = config.get("isSentence") or False

        if num_suggestions > 0 and is_sentence:
            raise ValueError(
                "Transliteration: numSuggestions is not valid for sentence-level transliteration"
            )

        # is_word_level = not isSentence: a boolean inversion the typed input
        # path cannot express, injected for the renderer (request.config.is_word_level).
        # top_k is a plain rename, handled in config (TOP_K reads numSuggestions).
        config["is_word_level"] = not is_sentence

    # output: adapter_config-driven (pair_with_input "input.source", include_config
    # false). Top-k suggestions arrive as extra Triton batch items, pairing with
    # "" once inputs run out — matching the contract.


__all__ = ["TransliterationTaskService"]
