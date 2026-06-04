"""
LanguageDiarizationTaskService — implements language diarization inference.

Extends AudioBase (base64 passthrough, adapter_config driven).
Overrides postprocess to produce the same
output structure as the old language-diarization-service.

Triton tensor contract (adapter_config from MMS):
  Inputs:  AUDIO_DATA (BYTES [1,1]) — base64 audio
           LANGUAGE   (BYTES [1,1]) — target language code, "" = all languages
  Output:  DIARIZATION_RESULT (BYTES) — JSON blob
"""

from typing import Any, Dict, List, Tuple

from services.base.audio_base import AudioBase
from services.base.task_service import PostProcessFormat


class LanguageDiarizationTaskService(AudioBase):
    """
    TaskService for Language Diarization inference.

    Inherits base64-passthrough preprocessing from AudioBase.
    Overrides convert_payload_to_triton_format (normalise target_language),
    and postprocess (parse DIARIZATION_RESULT JSON + envelope).
    """

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
        return await super().convert_payload_to_triton_format(input_data, config)

    async def postprocess_output(self, result: PostProcessFormat) -> Dict[str, Any]:
        output_list = []

        for item in result.response_data:
            # Try the well-known key first; fall back to the first value in the
            # dict so different adapter_config maps_to names still work.
            raw = item.get("diarization_json") or next(iter(item.values()), None)
            data = self._parse_json(raw)
            if not data:
                output_list.append({"total_segments": 0, "segments": [], "target_language": ""})
                continue

            segments = []
            for seg in data.get("segments", []):
                start = float(seg.get("start_time", 0.0))
                end = float(seg.get("end_time", 0.0))
                segments.append({
                    "start_time": start,
                    "end_time": end,
                    "duration": float(seg.get("duration", end - start)),
                    "language": str(seg.get("language", "")),
                    "confidence": float(seg.get("confidence", 0.0)),
                })
            segments.sort(key=lambda s: s["start_time"])

            output_list.append({
                "total_segments": len(segments),
                "segments": segments,
                "target_language": str(data.get("target_language", "")),
            })

        cfg = result.payload.get("config") or {}
        return {
            "taskType": "language-diarization",
            "output": output_list,
            "config": {"serviceId": cfg.get("serviceId")},
        }


__all__ = ["LanguageDiarizationTaskService"]
