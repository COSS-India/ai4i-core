"""NMT (Neural Machine Translation) TaskService."""
from typing import Any, Dict, Optional

from services.base.text_base import TextBase

_SMALL_THRESHOLD = 200
_MEDIUM_THRESHOLD = 1000


class NMTTaskService(TextBase):
    REQUIRES_TARGET_LANGUAGE = True  # enables target_language + not-equal check in base

    async def process(
        self,
        payload: Dict[str, Any],
        serviceInfo: Optional[Dict[str, Any]] = None,
    ) -> Any:
        return self._stub_response(payload)

    def _stub_response(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        from response_test.responses.nmt_responses import (
            SMALL_NMT_RESPONSE,
            MEDIUM_NMT_RESPONSE,
            LARGE_NMT_RESPONSE,
        )
        input_items = payload.get("input") or []
        total_length = sum(len(item.get("source", "")) for item in input_items)
        if total_length < _SMALL_THRESHOLD:
            return SMALL_NMT_RESPONSE
        if total_length < _MEDIUM_THRESHOLD:
            return MEDIUM_NMT_RESPONSE
        return LARGE_NMT_RESPONSE

    # postprocess_output: base default (source pairing + unwrap + config echo)
    # is the NMT contract — the /nmt route's response_model excludes config.


__all__ = ["NMTTaskService"]
