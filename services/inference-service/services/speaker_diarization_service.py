"""
SpeakerDiarizationTaskService — implements speaker diarization inference.

Extends AudioBase (base64 passthrough, adapter_config driven).
Overrides postprocess to produce the same
output structure as the old speaker-diarization-service.

Triton tensor contract (adapter_config from MMS):
  Inputs:  AUDIO_DATA   (BYTES [1,1]) — base64 audio
           NUM_SPEAKERS (BYTES [1,1]) — expected speaker count, "" = auto
  Output:  DIARIZATION_RESULT (BYTES) — JSON blob
"""

from typing import Any, Dict, List, Optional, Tuple

from services.base.audio_base import AudioBase
from services.base.task_service import PostProcessFormat

_SMALL_THRESHOLD = 200
_MEDIUM_THRESHOLD = 1000


class SpeakerDiarizationTaskService(AudioBase):
    """
    TaskService for Speaker Diarization inference.

    Inherits base64-passthrough preprocessing from AudioBase.
    Overrides convert_payload_to_triton_format (normalise num_speakers),
    and postprocess (parse DIARIZATION_RESULT JSON + envelope).
    """

    async def process(
        self,
        payload: Dict[str, Any],
        serviceInfo: Optional[Dict[str, Any]] = None,
    ) -> Any:
        return self._stub_response(payload)

    def _stub_response(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        from response_test.responses.speaker_diarization_responses import (
            SMALL_SPEAKER_DIARIZATION_RESPONSE,
            MEDIUM_SPEAKER_DIARIZATION_RESPONSE,
            LARGE_SPEAKER_DIARIZATION_RESPONSE,
        )
        audio_items = payload.get("audio") or []
        total_length = sum(
            len(item.get("audioContent") or item.get("audio_content", ""))
            for item in audio_items
        )
        if total_length < _SMALL_THRESHOLD:
            return SMALL_SPEAKER_DIARIZATION_RESPONSE
        if total_length < _MEDIUM_THRESHOLD:
            return MEDIUM_SPEAKER_DIARIZATION_RESPONSE
        return LARGE_SPEAKER_DIARIZATION_RESPONSE

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Normalise num_speakers to a string before mapper resolves the tensor."""
        config = dict(config)
        raw = config.get("num_speakers") or config.get("numSpeakers")
        config["num_speakers"] = "" if not raw else str(raw)
        return await super().convert_payload_to_triton_format(input_data, config)

    async def postprocess_output(self, result: PostProcessFormat) -> Dict[str, Any]:
        output_list = []

        for item in result.response_data:
            # Try the well-known key first; fall back to the first value in the
            # dict so different adapter_config maps_to names still work.
            raw = item.get("diarization_json") or next(iter(item.values()), None)
            data = self._parse_json(raw)
            if not data:
                output_list.append({"total_segments": 0, "num_speakers": 0, "speakers": [], "segments": []})
                continue

            segments = []
            speakers_set = set()
            for seg in data.get("segments", []):
                start = float(seg.get("start_time", 0.0))
                end = float(seg.get("end_time", 0.0))
                speaker = str(seg.get("speaker", ""))
                if speaker:
                    speakers_set.add(speaker)
                segments.append({
                    "start": start,
                    "end": end,
                    "duration": float(seg.get("duration", end - start)),
                    "speaker": speaker,
                })
            segments.sort(key=lambda s: s["start"])

            output_list.append({
                "total_segments": len(segments),
                "num_speakers": len(speakers_set),
                "speakers": sorted(speakers_set),
                "segments": segments,
            })

        cfg = result.payload.get("config") or {}
        return {
            "taskType": "speaker-diarization",
            "output": output_list,
            "config": {
                "serviceId": cfg.get("serviceId"),
                "language": cfg.get("language"),
            },
        }


__all__ = ["SpeakerDiarizationTaskService"]
