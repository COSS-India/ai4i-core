"""NMT (Neural Machine Translation) TaskService."""
import logging
from typing import Any, Dict, List, Optional
from services.base.text_base import TextBase
from services.base.config_mapper import GenericTritonMapper
from models.schemas.nmt import NMTInferenceResponse
logger = logging.getLogger(__name__)

class NMTTaskService(TextBase):
    def __init__(self, service_info=None, **deps):
        super().__init__(service_info=service_info)
        self.triton_client = None
        self.logger = logger

    async def validate_request(self, payload):
        await super().validate_request(payload)
        language = payload.get("config", {}).get("language", {})
        source_lang = language.get("source_language") or language.get("sourceLanguage")
        target_lang = language.get("target_language") or language.get("targetLanguage")
        if not source_lang or not target_lang:
            raise ValueError("NMT: sourceLanguage and targetLanguage are required")
        if source_lang == target_lang:
            raise ValueError("NMT: sourceLanguage and targetLanguage cannot be the same")
        self.logger.info(f"NMT: {source_lang} -> {target_lang} ({len(payload.get('input', []))} inputs)")

    def _get_inference_model_class(self):
        return GenericTritonMapper

    def _build_response(self, payload, postprocessed):
        return NMTInferenceResponse(output=postprocessed["output"], smr_response=None)

    async def postprocess_output(self, response_items, source_texts=None):
        from models.schemas.nmt import TranslationOutput
        paired = self._pair_with_sources(response_items, source_texts or [])
        output_list = [TranslationOutput(source=item["source"], target=item.get("target", "")) for item in paired]
        self.logger.debug(f"NMT post-processed {len(output_list)} translations")
        return {"output": output_list}

__all__ = ["NMTTaskService"]
