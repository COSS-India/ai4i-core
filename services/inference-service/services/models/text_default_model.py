"""
TextDefaultModel — default text inference model (NMT implementation).

Acts as the registered service class for NMT tasks. Can also be used
directly from the task registry for future simple text tasks that require
no custom postprocessing logic beyond adapter_config differences.

Common text pipeline (validate_request, preprocess_input, _get_inference_model_class,
_pair_with_sources, etc.) is inherited from TextBase.
"""

import logging
from typing import Any, Dict, List, Optional

from services.base.text_base import TextBase
from models.schemas.nmt import NMTInferenceResponse

logger = logging.getLogger(__name__)


class TextDefaultModel(TextBase):
    """
    Default text model — NMT (Neural Machine Translation) implementation.

    Registered in TASK_SERVICE_REGISTRY for task_type "NMT".
    Future simple text tasks (no custom postprocess logic) can also be
    registered directly against this class with their own adapter_config.
    """

    def __init__(self, service_info: Optional[Dict[str, Any]] = None, **kwargs: Any):
        super().__init__(service_info=service_info)
        self.logger = logger

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    async def validate_request(self, payload: Dict[str, Any]) -> None:
        await super().validate_request(payload)

        language = payload.get("config", {}).get("language", {})
        source_lang = language.get("source_language") or language.get("sourceLanguage")
        target_lang = language.get("target_language") or language.get("targetLanguage")

        if not source_lang or not target_lang:
            raise ValueError("NMT: sourceLanguage and targetLanguage are required")
        if source_lang == target_lang:
            raise ValueError("NMT: sourceLanguage and targetLanguage cannot be the same")

        self.logger.info(
            f"NMT: {source_lang} -> {target_lang} ({len(payload.get('input', []))} inputs)"
        )

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    async def postprocess_output(
        self,
        response_items: List[Dict[str, Any]],
        source_texts: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        from models.schemas.nmt import TranslationOutput

        paired = self._pair_with_sources(response_items, source_texts or [])
        output_list = [
            TranslationOutput(source=item["source"], target=item.get("target", ""))
            for item in paired
        ]
        self.logger.debug(f"NMT post-processed {len(output_list)} translations")
        return {"output": output_list}

    def _build_response(
        self, payload: Dict[str, Any], postprocessed: Dict[str, Any]
    ) -> NMTInferenceResponse:
        return NMTInferenceResponse(output=postprocessed["output"], smr_response=None)
