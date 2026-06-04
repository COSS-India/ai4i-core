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

from typing import Any, Dict, List, Tuple

from services.base.audio_base import AudioBase
from services.base.config_mapper import GenericTritonMapper


class SpeakerDiarizationTaskService(AudioBase):
    """
    TaskService for Speaker Diarization inference.

    Inherits base64-passthrough preprocessing from AudioBase.
    Overrides convert_payload_to_triton_format (normalise num_speakers),
    and postprocess (parse DIARIZATION_RESULT JSON + envelope).
    """

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Normalise num_speakers to a string before mapper resolves the tensor."""
        config = dict(config)
        raw = config.get("num_speakers") or config.get("numSpeakers")
        config["num_speakers"] = "" if not raw else str(raw)
        mapper = GenericTritonMapper(self._adapter_config)
        return mapper.compose_triton_kserve_v2_payload(
            input_data=input_data,
            config=config,
            context_builder=self._build_audio_context,
        )

    async def postprocess(
        self,
        payload: Dict[str, Any],
        response_items: List[Dict[str, Any]],
        source_texts: List[str],
    ) -> Dict[str, Any]:
        output_list = []

        for item in response_items:
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

        cfg = payload.get("config") or {}
        return {
            "taskType": "speaker-diarization",
            "output": output_list,
            "config": {
                "serviceId": cfg.get("serviceId"),
                "language": cfg.get("language"),
            },
        }


__all__ = ["SpeakerDiarizationTaskService"]
