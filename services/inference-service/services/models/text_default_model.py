"""NMT (Neural Machine Translation) TaskService."""
import logging
from typing import Any, Dict, List, Optional
from services.base.text_base import TextBase
from models.schemas.nmt import NMTInferenceResponse
logger = logging.getLogger(__name__)

class TextDefaultModel(TextBase):
    REQUIRES_TARGET_LANGUAGE = True  # enables target_language + not-equal check in base

    def __init__(self, service_info=None, **deps):
        super().__init__(service_info=service_info)
        self.logger = logger

    def _build_response(self, payload, postprocessed):
        return NMTInferenceResponse(output=postprocessed["output"], smr_response=None)

    async def postprocess_output(self, response_items, source_texts=None):
        from models.schemas.nmt import TranslationOutput
        paired = self._pair_with_sources(response_items, source_texts or [])
        output_list = [TranslationOutput(source=item["source"], target=item.get("target", "")) for item in paired]
        self.logger.debug(f"NMT post-processed {len(output_list)} translations")
        return {"output": output_list}

__all__ = ["TextDefaultModel"]
