"""Text-based TaskService implementations: NMT, NER, Transliteration, LanguageDetection."""

import logging
from typing import Any, Dict, List, Optional

from services.base.text_base import TextBase
from services.base.config_mapper import GenericTritonMapper
from models.schemas.nmt import NMTInferenceRequest, NMTInferenceResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# NMT
# ---------------------------------------------------------------------------

class NMTTaskService(TextBase):
    """TaskService for Neural Machine Translation inference."""

    def __init__(self, service_info: Optional[Dict[str, Any]] = None, **dependencies: Any):
        super().__init__(service_info=service_info)
        self.triton_client = None
        self.logger = logger

    async def _deserialize_payload(self, payload: Dict[str, Any]) -> NMTInferenceRequest:
        try:
            from models.schemas.nmt import TextInput, NMTConfig

            input_items = payload.get("input", [])
            if isinstance(input_items, list) and input_items:
                if isinstance(input_items[0], dict):
                    input_items = [TextInput(**item) for item in input_items]

            config_data = payload.get("config", {})
            if isinstance(config_data, dict):
                config_data = NMTConfig(**config_data)

            return NMTInferenceRequest(input=input_items, config=config_data)
        except Exception as e:
            raise ValueError(f"NMT: Failed to deserialize payload: {str(e)}")

    async def validate_request(self, request: Any) -> None:
        await super().validate_request(request)

        language = getattr(getattr(request, "config", None), "language", None)
        source_lang = getattr(language, "source_language", None)
        target_lang = getattr(language, "target_language", None)

        if not source_lang or not target_lang:
            raise ValueError("NMT: sourceLanguage and targetLanguage are required")
        if source_lang == target_lang:
            raise ValueError("NMT: sourceLanguage and targetLanguage cannot be the same")

        self.logger.info(f"NMT: {source_lang} -> {target_lang} ({len(request.input)} inputs)")

    def _get_inference_model_class(self) -> type:
        return GenericTritonMapper

    def _build_response(self, request: NMTInferenceRequest, postprocessed: Dict[str, Any]) -> NMTInferenceResponse:
        return NMTInferenceResponse(output=postprocessed["output"], smr_response=None)

    async def postprocess_output(
        self, response_items: List[Dict[str, Any]], source_texts: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        from models.schemas.nmt import TranslationOutput
        paired = self._pair_with_sources(response_items, source_texts or [])
        output_list = []
        for item in paired:
            target_text = item.get("target", "")
            if isinstance(target_text, bytes):
                target_text = target_text.decode("utf-8")
            output_list.append(TranslationOutput(source=item["source"], target=target_text))
        self.logger.debug(f"NMT post-processed {len(output_list)} translations")
        return {"output": output_list}


# ---------------------------------------------------------------------------
# NER
# ---------------------------------------------------------------------------

class NERTaskService(TextBase):
    """TaskService for Named Entity Recognition inference."""

    def __init__(self, service_info: Optional[Dict[str, Any]] = None, **dependencies: Any):
        super().__init__(service_info=service_info)
        self.logger = logger

    def _get_inference_model_class(self) -> type:
        return GenericTritonMapper


# ---------------------------------------------------------------------------
# Transliteration
# ---------------------------------------------------------------------------

class TransliterationTaskService(TextBase):
    """TaskService for Transliteration inference."""

    def __init__(self, service_info: Optional[Dict[str, Any]] = None, **dependencies: Any):
        super().__init__(service_info=service_info)
        self.logger = logger

    def _get_inference_model_class(self) -> type:
        return GenericTritonMapper


# ---------------------------------------------------------------------------
# Language Detection
# ---------------------------------------------------------------------------

class LanguageDetectionTaskService(TextBase):
    """TaskService for Language Detection inference."""

    def __init__(self, service_info: Optional[Dict[str, Any]] = None, **dependencies: Any):
        super().__init__(service_info=service_info)
        self.logger = logger

    def _get_inference_model_class(self) -> type:
        return GenericTritonMapper
