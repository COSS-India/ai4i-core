"""NMT (Neural Machine Translation) TaskService."""
import logging
from typing import Any, Dict, List, Optional
from services.base.text_base import TextBase

logger = logging.getLogger(__name__)

class TextDefaultModel(TextBase):
    REQUIRES_TARGET_LANGUAGE = True  # enables target_language + not-equal check in base

    def __init__(self, service_info=None, **deps):
        super().__init__(service_info=service_info)
        self.logger = logger

    def _build_response(self, payload, postprocessed):
        return {"output": postprocessed["output"]}

    async def postprocess_output(self, response_items, source_texts=None):
        paired = self._pair_with_sources(response_items, source_texts or [])
        output_list = []
        for item in paired:
            target = item.get("target", "")
            # Unwrap single-element list nesting from Triton KServe v2 responses
            while isinstance(target, (list, tuple)) and len(target) == 1:
                target = target[0]
            if isinstance(target, bytes):
                target = target.decode("utf-8", errors="replace")
            output_list.append({"source": item["source"], "target": str(target)})
        self.logger.debug(f"NMT post-processed {len(output_list)} translations")
        return {"output": output_list}

__all__ = ["TextDefaultModel"]
