"""Transliteration TaskService."""
from services.base.text_base import TextBase


class TransliterationTaskService(TextBase):
    REQUIRES_TARGET_LANGUAGE = True  # enables target_language + not-equal check in base

    async def validate_request(self, payload):
        await super().validate_request(payload)  # handles input + source/target language checks

        # --- Transliteration-specific: numSuggestions/isSentence + derived field injection ---
        config = payload.get("config", {})
        num_suggestions = config.get("numSuggestions") or 0
        is_sentence = config.get("isSentence") or False

        if num_suggestions > 0 and is_sentence:
            raise ValueError("Transliteration: numSuggestions is not valid for sentence-level transliteration")

        # Inject derived fields the renderer reads via value_path
        # (request.config.is_word_level / top_k): a boolean inversion + rename
        # the model needs but the typed input path cannot express.
        config["is_word_level"] = not is_sentence
        config["top_k"] = num_suggestions

        src = self._extract_source_lang(self._get_language(payload))
        tgt = self._extract_target_lang(self._get_language(payload))
        self.logger.info(f"Transliteration: {src} -> {tgt} (sentence={is_sentence}, top_k={num_suggestions}, {len(payload.get('input', []))} inputs)")

    # postprocess_output: adapter_config-driven (pair_with_input "input.source"
    # + include_config false). Top-k suggestions arrive as extra Triton batch
    # items, which pair with "" once inputs run out — matching the contract.

__all__ = ["TransliterationTaskService"]
