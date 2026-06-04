"""Audio Language Detection TaskService."""

import json
from typing import Any, Dict, List

from services.base.audio_base import AudioBase


class AudioLanguageDetectionTaskService(AudioBase):
    """
    TaskService for Audio Language Detection inference.

    Inherits base64-passthrough preprocessing and adapter_config-driven
    Triton I/O from AudioBase; only the response shape is ALD-specific.
    """

    async def build_response(self, payload, response_items, source_texts):
        cfg = payload.get("config") or {}
        return {
            "taskType": "audio-lang-detection",
            "output": self._unwrap_output_items(response_items),
            "config": {"serviceId": cfg.get("serviceId")},
        }

    def _unwrap_output_items(
        self, response_items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Unwrap single-element nested lists and decode bytes in each output item.

        Triton KServe v2 returns tensors as flat lists (e.g. shape [1,1] → ["hi"]).
        After GenericTritonMapper processes them they may still be wrapped in a list.
        Ensures the ALD output fields (language_code, confidence, all_scores) are
        plain scalars — confidence coerced to float, all_scores JSON-parsed.
        """
        unwrapped = []
        for item in response_items:
            clean = {}
            for key, value in item.items():
                value = self.unwrap_output_value(value)
                if key == "all_scores" and isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except (json.JSONDecodeError, ValueError):
                        pass
                if key == "confidence":
                    try:
                        value = float(value)
                    except (TypeError, ValueError):
                        pass
                clean[key] = value
            unwrapped.append(clean)
        return unwrapped


__all__ = ["AudioLanguageDetectionTaskService"]
