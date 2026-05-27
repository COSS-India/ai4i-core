"""
LanguageDiarizationTaskService — implements language diarization inference.

Extends AudioDefaultModel (base64 passthrough, adapter_config driven).
Overrides postprocess_output and _build_response to produce the same
output structure as the old language-diarization-service.

Triton tensor contract (adapter_config from MMS):
  Inputs:  AUDIO_DATA (BYTES [1,1]) — base64 audio
           LANGUAGE   (BYTES [1,1]) — target language code, "" = all languages
  Output:  DIARIZATION_RESULT (BYTES) — JSON blob
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from services.models.audio_default_model import AudioDefaultModel
from services.base.config_mapper import GenericTritonMapper

logger = logging.getLogger(__name__)


class LanguageDiarizationTaskService(AudioDefaultModel):
    """
    TaskService for Language Diarization inference.

    Inherits base64-passthrough preprocessing from AudioDefaultModel.
    Overrides convert_payload_to_triton_format (normalise target_language),
    postprocess_output (parse DIARIZATION_RESULT JSON), and _build_response.
    """

    def __init__(self, service_info: Optional[Dict[str, Any]] = None, **kwargs: Any):
        super().__init__(service_info=service_info, **kwargs)
        self.logger = logger

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Normalise target_language (camelCase or snake_case, defaults to "")."""
        config = dict(config)
        config["target_language"] = str(
            config.get("target_language") or config.get("targetLanguage") or ""
        )
        mapper = GenericTritonMapper(self._adapter_config)
        return mapper.compose_triton_kserve_v2_payload(
            input_data=input_data,
            config=config,
            context_builder=self._build_audio_context,
        )

    async def postprocess_output(
        self, response_items: List[Dict[str, Any]], **kwargs: Any
    ) -> Dict[str, Any]:
        output_list = []

        for item in response_items:
            data = self._parse_json(item.get("diarization_json"))
            if not data:
                output_list.append({"total_segments": 0, "segments": [], "target_language": ""})
                continue

            segments = []
            for seg in data.get("segments", []):
                start = float(seg.get("start_time", 0.0))
                end = float(seg.get("end_time", 0.0))
                segments.append({
                    "start": start,
                    "end": end,
                    "duration": float(seg.get("duration", end - start)),
                    "language": str(seg.get("language", "")),
                    "confidence": float(seg.get("confidence", 0.0)),
                })
            segments.sort(key=lambda s: s["start"])

            output_list.append({
                "total_segments": len(segments),
                "segments": segments,
                "target_language": str(data.get("target_language", "")),
            })

        return {"output": output_list}

    def _build_response(
        self, payload: Dict[str, Any], postprocessed: Dict[str, Any]
    ) -> Dict[str, Any]:
        service_id = (payload.get("config") or {}).get("serviceId")
        result = {"taskType": "language-diarization", "output": postprocessed["output"]}
        if service_id:
            result["config"] = {"serviceId": service_id}
        return result

    def _parse_json(self, value: Any) -> Dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        if isinstance(value, str):
            try:
                return json.loads(value) or {}
            except json.JSONDecodeError:
                logger.warning("%s: failed to parse diarization JSON: %r", self.task_name, value[:200])
                return {}
        return {}


__all__ = ["LanguageDiarizationTaskService"]
