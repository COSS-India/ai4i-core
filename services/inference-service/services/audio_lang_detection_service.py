"""Audio Language Detection TaskService."""

from typing import Any, Dict, Optional

from services.base.audio_base import AudioBase

_SMALL_THRESHOLD = 200
_MEDIUM_THRESHOLD = 1000


class AudioLanguageDetectionTaskService(AudioBase):
    """
    TaskService for Audio Language Detection inference.

    Fully adapter_config-driven: AudioBase handles base64-passthrough
    preprocessing and Triton I/O; the adapter parses ALL_SCORES via
    transform "json_parse" and the response envelope declares
    task_type + config_keys ["serviceId"]. The base default
    postprocess_output applies that shaping — no code here.
    """

    async def process(
        self,
        payload: Dict[str, Any],
        serviceInfo: Optional[Dict[str, Any]] = None,
    ) -> Any:
        return self._stub_response(payload)

    def _stub_response(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        from response_test.responses.audio_lang_detection_responses import (
            SMALL_AUDIO_LANG_DETECTION_RESPONSE,
            MEDIUM_AUDIO_LANG_DETECTION_RESPONSE,
            LARGE_AUDIO_LANG_DETECTION_RESPONSE,
        )
        audio_items = payload.get("audio") or []
        total_length = sum(
            len(item.get("audioContent") or item.get("audio_content", ""))
            for item in audio_items
        )
        if total_length < _SMALL_THRESHOLD:
            return SMALL_AUDIO_LANG_DETECTION_RESPONSE
        if total_length < _MEDIUM_THRESHOLD:
            return MEDIUM_AUDIO_LANG_DETECTION_RESPONSE
        return LARGE_AUDIO_LANG_DETECTION_RESPONSE


__all__ = ["AudioLanguageDetectionTaskService"]
