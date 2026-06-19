"""Language Detection TaskService."""
from typing import Any, Dict, Optional

from services.base.text_base import TextBase

_SMALL_THRESHOLD = 200
_MEDIUM_THRESHOLD = 1000


class LanguageDetectionTaskService(TextBase):
    # No language config required — language is DETECTED not specified.
    # Base validate_request handles input existence; language block skipped.
    #
    # Output is adapter_config-driven: transform ["json_parse", "wrap_list"]
    # turns the model's JSON prediction string into [prediction], and
    # pair_with_input "input.source" pairs each item with its input text.
    # The base default postprocess_output applies that shaping — no code here.

    async def process(
        self,
        payload: Dict[str, Any],
        serviceInfo: Optional[Dict[str, Any]] = None,
    ) -> Any:
        return self._stub_response(payload)

    def _stub_response(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        from response_test.responses.language_detection_responses import (
            SMALL_LANGUAGE_DETECTION_RESPONSE,
            MEDIUM_LANGUAGE_DETECTION_RESPONSE,
            LARGE_LANGUAGE_DETECTION_RESPONSE,
        )
        input_items = payload.get("input") or []
        total_length = sum(len(item.get("source", "")) for item in input_items)
        if total_length < _SMALL_THRESHOLD:
            return SMALL_LANGUAGE_DETECTION_RESPONSE
        if total_length < _MEDIUM_THRESHOLD:
            return MEDIUM_LANGUAGE_DETECTION_RESPONSE
        return LARGE_LANGUAGE_DETECTION_RESPONSE


__all__ = ["LanguageDetectionTaskService"]
