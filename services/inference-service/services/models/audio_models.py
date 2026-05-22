"""
Audio model service implementations.

Each class inherits the full pipeline from AudioBase.
Model classes are minimal — they only implement:
  _deserialize_payload       → task-specific request model
  validate_request           → opt-in validation hooks (e.g. sourceLanguage)
  _resolve_service_and_model → task-specific service ID + adapter config fallback
  _create_inference_model    → factory: return the right InferenceModel subclass
  postprocess_output         → task-specific output wrapping
  _build_response            → return the typed response model

run_inference is owned by AudioBase (Template Method) and must NOT be overridden
unless a task has genuinely different Triton call semantics.
"""

from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel

from services.base.audio_base import AudioBase
from models.schemas.asr import (
    ASRConfig,
    ASRInferenceRequest,
    ASRInferenceResponse,
    AudioInput,
)
from inference_models.config_mapper import GenericTritonMapper  # type: ignore[import]


# ---------------------------------------------------------------------------
# Fallback adapter config for asr_am_ensemble when model management does not
# return one.  Matches the tensor contract of the hosted ensemble:
#   asr_preprocessor → asr_am → asr_greedy_decoder
# ---------------------------------------------------------------------------
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

# Default service ID used when the request carries no serviceId.
_DEFAULT_ASR_SERVICE_ID = "28e6a160dd9f38e830dd5c98ec3736ee"  # SHA256("asr-gpu")[:32]


class ASRDefaultModel(AudioBase):
    """
    Default ASR model service (asr_am_ensemble).

    Full pipeline (inherited from AudioBase unless noted):
      _deserialize_payload       → ASRInferenceRequest              [overridden]
      validate_request           → _validate_audio_items
                                   + _validate_source_language      [overridden]
      preprocess_input           → bytes → decode → stereo→mono
                                   → resample → equalize → dequantize
      _resolve_service_and_model → ASR default ID + adapter fallback [overridden]
      run_inference              → Template Method (AudioBase)
        _create_inference_model  → ASRInferenceModel                [overridden]
        postprocess_output       → decode bytes → TranscriptionOutput[overridden]
        _build_response          → ASRInferenceResponse             [overridden]

    Override guide:
      - Same tensor contract, new endpoint → no code change, update DB only.
      - Different payload structure (e.g. INT32 instead of FP32) → subclass
        AudioBase and override convert_payload_to_triton_format (+ adapter config).
    """

    # ------------------------------------------------------------------
    # Deserialise
    # ------------------------------------------------------------------

    async def _deserialize_payload(self, payload: Dict[str, Any]) -> ASRInferenceRequest:
        """Parse the raw request dict into an ASRInferenceRequest model."""
        try:
            audio_items = payload.get("audio", [])
            if isinstance(audio_items, list) and audio_items:
                if isinstance(audio_items[0], dict):
                    audio_items = [AudioInput(**item) for item in audio_items]

            config_data = payload.get("config", {})
            if isinstance(config_data, dict):
                config_data = ASRConfig(**config_data)

            return ASRInferenceRequest(audio=audio_items, config=config_data)
        except Exception as exc:
            raise ValueError(f"ASR: failed to deserialize payload: {exc}") from exc

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------

    async def validate_request(self, request: BaseModel) -> None:
        """
        Extends AudioBase validation with ASR-specific check:
          super() → _validate_audio_items
          + _validate_source_language (ASR opt-in)
        """
        await super().validate_request(request)
        await self._validate_source_language(request)

    # ------------------------------------------------------------------
    # Service resolution (ASR-specific override)
    # ------------------------------------------------------------------

    async def _resolve_service_and_model(
        self, config: ASRConfig
    ) -> Tuple[str, str, str, Optional[str], Optional[Any]]:
        """
        Resolve service_id → (service_id, model_name, triton_endpoint, api_key, adapter_config).

        Differences from BaseTaskService default:
          - Uses ASR-specific default service_id when none is given.
          - Falls back to _DEFAULT_ASR_ADAPTER_CONFIG when model management
            does not return an adapter_config (keeps existing services working).
        """
        service_id = config.service_id
        if not service_id:
            service_id = _DEFAULT_ASR_SERVICE_ID
            self.logger.warning(
                "ASR: no serviceId in request, using default: %s", service_id
            )

        try:
            service_info = await self.inference_server_resolver.resolve_service(service_id)
        except Exception as exc:
            raise RuntimeError(
                f"ASR: failed to resolve service '{service_id}': {exc}"
            ) from exc

        model_name      = service_info.get("name", "")
        triton_endpoint = service_info.get("endpoint", "")
        api_key         = service_info.get("api_key")
        adapter_config  = service_info.get("adapter_config")

        if not model_name or not triton_endpoint:
            raise RuntimeError(
                "ASR: service resolver returned incomplete info "
                f"(name={model_name!r}, endpoint={triton_endpoint!r})"
            )

        if not adapter_config:
            self.logger.warning(
                "ASR: adapter_config not returned by model management for service '%s' "
                "— falling back to default asr_am_ensemble config",
                service_id,
            )
            adapter_config = _DEFAULT_ASR_ADAPTER_CONFIG

        return service_id, model_name, triton_endpoint, api_key, adapter_config

    # ------------------------------------------------------------------
    # run_inference hooks
    # ------------------------------------------------------------------

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Convert preprocessed audio item(s) to KServe v2 Triton inputs via GenericTritonMapper."""
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
        """Convert raw Triton output to a list of transcript dicts via GenericTritonMapper."""
        mapper = GenericTritonMapper(self._adapter_config)
        mapped = mapper.map_outputs(triton_output)
        return mapper.to_output_items(mapped)

    def _build_audio_context(
        self,
        item: Dict[str, Any],
        index: int,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build the audio context dict consumed by value_path declarations in the adapter config."""
        samples = item.get("samples") or []
        return {
            "audio": {
                "samples":     samples,
                "num_samples": item.get("num_samples", len(samples)),
                "sample_rate": item.get("sample_rate"),
            }
        }

    def _build_response(
        self, request: BaseModel, postprocessed: Dict[str, Any]
    ) -> ASRInferenceResponse:
        """Wrap postprocessed transcriptions in the typed ASR response."""
        return ASRInferenceResponse(output=postprocessed["output"])

    # ------------------------------------------------------------------
    # Postprocess
    # ------------------------------------------------------------------

    async def postprocess_output(
        self, response_items: List[Dict[str, Any]], **kwargs: Any
    ) -> Dict[str, Any]:
        """
        ASR postprocess:
          _decode_output_bytes → _wrap_transcription_output
        """
        decoded = await self._decode_output_bytes(response_items)
        return await self._wrap_transcription_output(decoded)


# ---------------------------------------------------------------------------
# Future audio task default models — to be implemented in upcoming PRs
# ---------------------------------------------------------------------------

class AudioLangDetectionDefaultModel(AudioBase):
    """
    Default Audio Language Detection model service.
    Will override: preprocess_input (uses _resolve_audio_base64 instead of float decode).
    """
    pass


class SpeakerDiarizationDefaultModel(AudioBase):
    """
    Default Speaker Diarization model service.
    Will override: preprocess_input (uses _resolve_audio_base64),
                   postprocess_output (different response schema),
                   _empty_output (no segments/speakers).
    """
    pass


class LanguageDiarizationDefaultModel(AudioBase):
    """
    Default Language Diarization model service.
    Will override: preprocess_input (uses _resolve_audio_base64),
                   postprocess_output (different response schema),
                   _empty_output (target_language fallback).
    """
    pass
