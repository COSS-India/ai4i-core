"""Language Detection TaskService."""
import json
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
        as a list of prediction objects: [{langCode, scriptCode, langScore, language}, ...]
        """
        output_list = []
        sources = source_texts or []
        items = response_items if isinstance(response_items, list) else [response_items]
        for idx, item in enumerate(items):
            raw_value = item.get("langPrediction", "") if isinstance(item, dict) else item
            # Unwrap Triton KServe v2 nesting: only peel [bytes] or [string] wrappers
            while isinstance(raw_value, (list, tuple)) and len(raw_value) == 1 and isinstance(raw_value[0], (bytes, str)):
                raw_value = raw_value[0]
            if isinstance(raw_value, bytes):
                raw_value = raw_value.decode("utf-8", errors="replace")
            # Parse JSON-encoded prediction string into a list of prediction objects
            if isinstance(raw_value, str):
                try:
                    raw_value = json.loads(raw_value)
                except (json.JSONDecodeError, ValueError):
                    raw_value = raw_value.strip()
            # Always return langPrediction as a list
            if not isinstance(raw_value, list):
                raw_value = [raw_value] if raw_value else []
            source = sources[idx] if idx < len(sources) else ""
            output_list.append({"source": source, "langPrediction": raw_value})
        self.logger.debug(f"LANGUAGE_DETECTION post-processed {len(output_list)} results")
        return {"output": output_list}

    def _build_response(self, payload, postprocessed):
        return postprocessed


__all__ = ["LanguageDetectionTaskService"]
