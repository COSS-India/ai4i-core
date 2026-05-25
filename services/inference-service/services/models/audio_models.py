"""
Audio TaskService implementations: ASR, and stubs for ALD, Speaker Diarization,
Language Diarization (each to be fleshed out in their own PR).
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from services.base.audio_base import AudioBase
from services.base.config_mapper import GenericTritonMapper
from models.schemas.asr import (
    ASRInferenceResponse,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ASR
# ---------------------------------------------------------------------------

# Fallback adapter config for asr_am_ensemble when MMS does not return one.
# Tensor contract: asr_preprocessor → asr_am → asr_greedy_decoder
_DEFAULT_ASR_ADAPTER_CONFIG = {
    "version": "1",
    "model_version": "1",
    "inputs": [
        {
            "tensor": "AUDIO_SIGNAL",
            "dtype":  "FP32",
            "shape":  [-1, -1],
            "value":  "audio.samples",
        },
        {
            "tensor": "NUM_SAMPLES",
            "dtype":  "INT32",
            "shape":  [-1, 1],
            "value":  "audio.num_samples",
        },
        {
            "tensor": "LANG_ID",
            "dtype":  "BYTES",
            "shape":  [-1, 1],
            "value":  "request.config.language.source_language",
        },
    ],
    "outputs": [
        {
            "tensor":  "TRANSCRIPTS",
            "dtype":   "BYTES",
            "maps_to": "transcript",
        },
    ],
}


class ASRTaskService(AudioBase):
    """
    TaskService for Automatic Speech Recognition inference.

    Inherits the full audio pipeline from AudioBase:
      validate_request  → audio items present + source_language set
      preprocess_input  → bytes → decode → mono → resample → equalize → dequantize
      execute_triton_inference (AudioBase) → per-item Triton loop using service_info
      postprocess_output → decode bytes → TranscriptionOutput list
      _build_response   → ASRInferenceResponse

    service_info is injected by the Orchestrator before construction —
    no internal resolver calls.
    """

    def __init__(self, service_info: Optional[Dict[str, Any]] = None, **kwargs: Any):
        super().__init__(service_info=service_info, **kwargs)
        self.logger = logger

    async def validate_request(self, payload: Dict[str, Any]) -> None:
        """AudioBase validation + ASR-specific sourceLanguage check."""
        await super().validate_request(payload)
        await self._validate_source_language(payload)

    def _get_default_adapter_config(self) -> Dict[str, Any]:
        return _DEFAULT_ASR_ADAPTER_CONFIG

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Convert one preprocessed audio item to KServe v2 Triton inputs."""
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
        """Map raw Triton output to a list of transcript dicts."""
        mapper = GenericTritonMapper(self._adapter_config)
        mapped = mapper.map_outputs(triton_output)
        return mapper.to_output_items(mapped)

    def _build_audio_context(
        self,
        item: Dict[str, Any],
        index: int,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build the audio context dict used by value_path declarations in adapter config."""
        samples = item.get("samples") or []
        return {
            "audio": {
                "samples":     samples,
                "num_samples": item.get("num_samples", len(samples)),
                "sample_rate": item.get("sample_rate"),
            }
        }

    async def postprocess_output(
        self, response_items: List[Dict[str, Any]], **kwargs: Any
    ) -> Dict[str, Any]:
        """Decode bytes output → wrap in TranscriptionOutput list."""
        decoded = await self._decode_output_bytes(response_items)
        return await self._wrap_transcription_output(decoded)

    def _build_response(
        self, payload: Dict[str, Any], postprocessed: Dict[str, Any]
    ) -> ASRInferenceResponse:
        return ASRInferenceResponse(output=postprocessed["output"], smr_response=None)


# ---------------------------------------------------------------------------
# Stubs — each to be fleshed out in its own PR
# ---------------------------------------------------------------------------

class AudioLangDetectionDefaultModel(AudioBase):
    """
    Default Audio Language Detection model service.
    Will override: preprocess_input (base64 passthrough instead of float decode).
    """
    pass


class SpeakerDiarizationDefaultModel(AudioBase):
    """
    Default Speaker Diarization model service.
    Will override: preprocess_input (base64 passthrough),
                   postprocess_output (speaker segments schema),
                   _get_default_adapter_config.
    """
    pass


class LanguageDiarizationDefaultModel(AudioBase):
    """
    Default Language Diarization model service.
    Will override: preprocess_input (base64 passthrough),
                   postprocess_output (language segments schema),
                   _get_default_adapter_config.
    """
    pass
