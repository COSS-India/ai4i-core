"""Transliteration TaskService."""
from services.base.text_base import TextBase
from services.base.task_service import PostProcessFormat


class TransliterationTaskService(TextBase):
    REQUIRES_TARGET_LANGUAGE = True  # enables target_language + not-equal check in base

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

    async def postprocess_output(self, result: PostProcessFormat):
        paired = self._pair_with_sources(result.response_data, result.source_texts)
        output_list = []
        for item in paired:
            target_raw = item.get("target", "")
            # target may be a top-k suggestion list — contract returns the first
            target_text = target_raw[0] if isinstance(target_raw, list) else (target_raw or "")
            output_list.append({"source": item["source"], "target": target_text})
        self.logger.debug(f"Transliteration post-processed {len(output_list)} results")
        return {"output": output_list}

__all__ = ["TransliterationTaskService"]
