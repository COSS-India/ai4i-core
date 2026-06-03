"""
Audio task services — concrete classes for the audio task types.

  ASRTaskService                  — float-PCM pipeline (extends AudioBase)
  LanguageDiarizationTaskService  — base64 passthrough (extends _DiarizationBase)
  SpeakerDiarizationTaskService   — base64 passthrough (extends _DiarizationBase)

_DiarizationBase holds the shared diarization pipeline: normalize config →
mapper-driven Triton I/O (inherited from AudioDefaultModel) → parse the
DIARIZATION_RESULT JSON blob → shape segments. Subclasses provide only the
task-specific config normalization, segment shape, and response envelope.

Triton tensor contract for diarization (adapter_config from MMS):
  Inputs:  AUDIO_DATA (BYTES [1,1]) — base64 audio
           LANGUAGE / NUM_SPEAKERS (BYTES [1,1]) — task-specific control input
  Output:  DIARIZATION_RESULT (BYTES) — JSON blob
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from services.base.audio_base import AudioBase, AudioDefaultModel
from services.base.config_mapper import GenericTritonMapper

logger = logging.getLogger(__name__)


class ASRTaskService(AudioBase):
    """
    TaskService for Automatic Speech Recognition.

    Extends AudioBase with ASR-specific behaviour:
      validate_request                  → adds sourceLanguage check
      convert_payload_to_triton_format  → GenericTritonMapper + _build_audio_context
      convert_triton_output_to_task_format → GenericTritonMapper output mapping
      postprocess_output                → decode bytes → TranscriptionOutput list
      _build_response                   → ASRInferenceResponse

    preprocess_input is inherited from AudioBase:
      bytes → decode → mono → resample (16 kHz) → equalize → dequantize

    service_info (including adapter_config) is injected by the Orchestrator.
    """

    def __init__(self, service_info: Optional[Dict[str, Any]] = None, **kwargs: Any):
        super().__init__(service_info=service_info, **kwargs)
        self.logger = logger

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    async def validate_request(self, payload: Dict[str, Any]) -> None:
        """AudioBase validation + sourceLanguage check."""
        await super().validate_request(payload)
        await self._validate_source_language(payload)

    # ------------------------------------------------------------------
    # Triton format hooks
    # ------------------------------------------------------------------

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Build KServe v2 inputs from preprocessed float PCM samples.

        Normalises config.language to always expose source_language (snake_case)
        so the adapter_config path 'request.config.language.source_language' resolves
        regardless of whether the frontend sends sourceLanguage (camelCase) or a
        plain language string.
        """
        config = dict(config)
        language = config.get("language", {})
        if isinstance(language, dict):
            source_lang = (
                language.get("source_language") or language.get("sourceLanguage") or ""
            )
            config["language"] = {"source_language": str(source_lang)}
        elif isinstance(language, str):
            config["language"] = {"source_language": language}

        mapper = GenericTritonMapper(self._adapter_config)
        return mapper.compose_triton_kserve_v2_payload(
            input_data=input_data,
            config=config,
            context_builder=self._build_audio_context,
        )

    async def convert_triton_output_to_task_format(
        self,
        triton_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Map raw Triton output tensors to a list of transcript dicts."""
        mapper = GenericTritonMapper(self._adapter_config)
        mapped = mapper.map_outputs(triton_output)
        return mapper.to_output_items(mapped)

    def _build_audio_context(
        self,
        item: Dict[str, Any],
        index: int,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Context dict fed to adapter_config value_path resolution.
        Exposes audio.samples, audio.num_samples, audio.sample_rate —
        populated by AudioBase.preprocess_input before the Triton loop.
        """
        samples = item.get("samples") or []
        return {
            "audio": {
                "samples":     samples,
                "num_samples": item.get("num_samples", len(samples)),
                "sample_rate": item.get("sample_rate"),
            }
        }

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    async def postprocess_output(
        self, response_items: List[Dict[str, Any]], **kwargs: Any
    ) -> Dict[str, Any]:
        """Decode bytes → wrap in TranscriptionOutput list."""
        decoded = await self._decode_output_bytes(response_items)
        return await self._wrap_transcription_output(
            decoded, source_texts=kwargs.get("source_texts", [])
        )

    def _build_response(
        self, payload: Dict[str, Any], postprocessed: Dict[str, Any]
    ) -> Dict[str, Any]:
        return postprocessed


class _DiarizationBase(AudioDefaultModel):
    """
    Shared pipeline for diarization tasks (language / speaker).

    Inherits base64-passthrough preprocessing and mapper-driven Triton I/O
    from AudioDefaultModel. Implements the common postprocess flow:
    parse DIARIZATION_RESULT JSON → shape each segment → finalize per item.

    Subclasses implement:
      _normalize_config(config) → task-specific control input (target_language / num_speakers)
      _empty_item()             → fallback dict when Triton returns no data
      _shape_segment(seg)       → per-segment field shape
      _finalize(segments, data) → sorting + aggregation + per-item envelope
      _build_response(...)      → taskType envelope
    """

    def __init__(self, service_info: Optional[Dict[str, Any]] = None, **kwargs: Any):
        super().__init__(service_info=service_info, **kwargs)
        self.logger = logger

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Apply task-specific config normalization, then compose via adapter_config."""
        config = self._normalize_config(dict(config))
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
            # Try the well-known key first; fall back to the first value in the
            # dict so different adapter_config maps_to names still work.
            raw = item.get("diarization_json") or next(iter(item.values()), None)
            data = self._parse_json(raw)
            if not data:
                output_list.append(self._empty_item())
                continue

            segments = [self._shape_segment(seg) for seg in data.get("segments", [])]
            output_list.append(self._finalize(segments, data))

        return {"output": output_list}

    def _parse_json(self, value: Any) -> Dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        # Unwrap single-element list nesting from Triton KServe v2 responses
        # e.g. to_output_items peels [["json"]] → ["json"]; we peel once more → "json"
        while isinstance(value, (list, tuple)) and len(value) == 1:
            value = value[0]
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        if isinstance(value, str):
            try:
                return json.loads(value) or {}
            except json.JSONDecodeError:
                logger.warning("%s: failed to parse diarization JSON: %r", self.task_name, value[:200])
                return {}
        return {}

    # ------------------------------------------------------------------
    # Hooks — subclasses must implement these
    # ------------------------------------------------------------------

    def _normalize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _normalize_config"
        )

    def _empty_item(self) -> Dict[str, Any]:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _empty_item"
        )

    def _shape_segment(self, seg: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _shape_segment"
        )

    def _finalize(
        self, segments: List[Dict[str, Any]], data: Dict[str, Any]
    ) -> Dict[str, Any]:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _finalize"
        )


class LanguageDiarizationTaskService(_DiarizationBase):
    """
    TaskService for Language Diarization inference.

    Control input: LANGUAGE — target language code, "" = all languages.
    Segment shape: start_time / end_time / duration / language / confidence.
    """

    def _normalize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Normalise target_language (camelCase or snake_case, defaults to "")."""
        config["target_language"] = str(
            config.get("target_language") or config.get("targetLanguage") or ""
        )
        return config

    def _empty_item(self) -> Dict[str, Any]:
        return {"total_segments": 0, "segments": [], "target_language": ""}

    def _shape_segment(self, seg: Dict[str, Any]) -> Dict[str, Any]:
        start = float(seg.get("start_time", 0.0))
        end = float(seg.get("end_time", 0.0))
        return {
            "start_time": start,
            "end_time": end,
            "duration": float(seg.get("duration", end - start)),
            "language": str(seg.get("language", "")),
            "confidence": float(seg.get("confidence", 0.0)),
        }

    def _finalize(
        self, segments: List[Dict[str, Any]], data: Dict[str, Any]
    ) -> Dict[str, Any]:
        segments.sort(key=lambda s: s["start_time"])
        return {
            "total_segments": len(segments),
            "segments": segments,
            "target_language": str(data.get("target_language", "")),
        }

    def _build_response(
        self, payload: Dict[str, Any], postprocessed: Dict[str, Any]
    ) -> Dict[str, Any]:
        cfg = payload.get("config") or {}
        return {
            "taskType": "language-diarization",
            "output": postprocessed["output"],
            "config": {"serviceId": cfg.get("serviceId")},
        }


class SpeakerDiarizationTaskService(_DiarizationBase):
    """
    TaskService for Speaker Diarization inference.

    Control input: NUM_SPEAKERS — expected speaker count, "" = auto.
    Segment shape: start / end / duration / speaker, plus speakers aggregation.
    """

    def _normalize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Normalise num_speakers to a string before mapper resolves the tensor."""
        raw = config.get("num_speakers") or config.get("numSpeakers")
        config["num_speakers"] = "" if not raw else str(raw)
        return config

    def _empty_item(self) -> Dict[str, Any]:
        return {"total_segments": 0, "num_speakers": 0, "speakers": [], "segments": []}

    def _shape_segment(self, seg: Dict[str, Any]) -> Dict[str, Any]:
        start = float(seg.get("start_time", 0.0))
        end = float(seg.get("end_time", 0.0))
        return {
            "start": start,
            "end": end,
            "duration": float(seg.get("duration", end - start)),
            "speaker": str(seg.get("speaker", "")),
        }

    def _finalize(
        self, segments: List[Dict[str, Any]], data: Dict[str, Any]
    ) -> Dict[str, Any]:
        segments.sort(key=lambda s: s["start"])
        speakers = sorted({s["speaker"] for s in segments if s["speaker"]})
        return {
            "total_segments": len(segments),
            "num_speakers": len(speakers),
            "speakers": speakers,
            "segments": segments,
        }

    def _build_response(
        self, payload: Dict[str, Any], postprocessed: Dict[str, Any]
    ) -> Dict[str, Any]:
        cfg = payload.get("config") or {}
        return {
            "taskType": "speaker-diarization",
            "output": postprocessed["output"],
            "config": {
                "serviceId": cfg.get("serviceId"),
                "language": cfg.get("language"),
            },
        }


__all__ = [
    "ASRTaskService",
    "LanguageDiarizationTaskService",
    "SpeakerDiarizationTaskService",
]
