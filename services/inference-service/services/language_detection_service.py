"""Language Detection TaskService."""
import logging
from typing import Any, Dict, List, Optional
from services.base.text_base import TextBase

logger = logging.getLogger(__name__)


class LanguageDetectionTaskService(TextBase):
    # No language config required — language is DETECTED not specified
    # Base validate_request handles input existence; language block skipped.

    def __init__(self, service_info=None, **deps):
        super().__init__(service_info=service_info)
        self.logger = logger

    async def postprocess_output(self, response_items, source_texts=None):
        """
        Return output items with 'source' (input text) and 'langPrediction'
        (raw Triton output, unwrapped) so the frontend receives exactly the
        fields it validates against.
        """
        output_list = []
        sources = source_texts or []
        items = response_items if isinstance(response_items, list) else [response_items]
        for idx, item in enumerate(items):
            raw_value = item.get("langPrediction", "") if isinstance(item, dict) else item
            # Unwrap single-element list nesting from Triton KServe v2 responses
            while isinstance(raw_value, (list, tuple)) and len(raw_value) == 1:
                raw_value = raw_value[0]
            if isinstance(raw_value, bytes):
                raw_value = raw_value.decode("utf-8", errors="replace")
            source = sources[idx] if idx < len(sources) else ""
            output_list.append({"source": source, "langPrediction": str(raw_value).strip()})
        self.logger.debug(f"LANGUAGE_DETECTION post-processed {len(output_list)} results")
        return {"output": output_list}

    def _build_response(self, payload, postprocessed):
        return postprocessed


__all__ = ["LanguageDetectionTaskService"]
