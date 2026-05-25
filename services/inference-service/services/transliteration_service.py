"""Transliteration TaskService."""
import logging
from typing import Any, Dict, List, Optional
from services.base.text_base import TextBase
from services.base.config_mapper import GenericTritonMapper
from models.schemas.transliteration import TransliterationInferenceResponse
logger = logging.getLogger(__name__)

class TransliterationTaskService(TextBase):
    def __init__(self, service_info=None, **deps):
        super().__init__(service_info=service_info)
        self.logger = logger

    def _get_inference_model_class(self):
        return GenericTritonMapper

    async def validate_request(self, payload):
        await super().validate_request(payload)
        config = payload.get("config", {})
        language = config.get("language", {})
        source_lang = language.get("source_language") or language.get("sourceLanguage")
        target_lang = language.get("target_language") or language.get("targetLanguage")
        if not source_lang or not target_lang:
            raise ValueError("Transliteration: source_language and target_language are required")
        if source_lang == target_lang:
            raise ValueError("Transliteration: source_language and target_language cannot be the same")
        num_suggestions = config.get("num_suggestions") or config.get("numSuggestions") or 0
        is_sentence = config.get("is_sentence") or config.get("isSentence") or False
        if num_suggestions > 0 and is_sentence:
            raise ValueError("Transliteration: numSuggestions is not valid for sentence-level transliteration")
        # Inject derived fields so mapper can resolve value_path: request.config.is_word_level/top_k
        config["is_word_level"] = not is_sentence
        config["top_k"] = num_suggestions
        self.logger.info(f"Transliteration: {source_lang} -> {target_lang} (sentence={is_sentence}, top_k={num_suggestions}, {len(payload.get('input', []))} inputs)")

    def _build_response(self, payload, postprocessed):
        return TransliterationInferenceResponse(output=postprocessed["output"])

    async def postprocess_output(self, response_items, source_texts=None):
        from models.schemas.transliteration import TransliterationOutput
        paired = self._pair_with_sources(response_items, source_texts or [])
        output_list = []
        for item in paired:
            target_raw = item.get("target", "")
            target_text = target_raw[0] if isinstance(target_raw, list) else (target_raw or "")
            output_list.append(TransliterationOutput(source=item["source"], target=target_text))
        self.logger.debug(f"Transliteration post-processed {len(output_list)} results")
        return {"output": output_list}

__all__ = ["TransliterationTaskService"]
