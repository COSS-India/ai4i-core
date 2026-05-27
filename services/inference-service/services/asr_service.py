"""ASR TaskService — Automatic Speech Recognition inference."""

import logging
from typing import Any, Dict, List, Optional, Tuple

from services.base.audio_base import AudioBase
from services.base.config_mapper import GenericTritonMapper
from models.schemas.asr import ASRInferenceResponse

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
        """Build KServe v2 inputs from preprocessed float PCM samples."""
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
        return await self._wrap_transcription_output(decoded)

    def _build_response(
        self, payload: Dict[str, Any], postprocessed: Dict[str, Any]
    ) -> ASRInferenceResponse:
        return ASRInferenceResponse(output=postprocessed["output"], smr_response=None)
