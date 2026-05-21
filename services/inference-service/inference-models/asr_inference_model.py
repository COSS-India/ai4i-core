"""ASR (Automatic Speech Recognition) InferenceModel using generic mapper."""

import base64
from typing import Any, Dict, List, Optional, Tuple, Union

from inference_models.base_inference_model import InferenceModel, InferenceModelError
from inference_models.config_mapper import AdapterMappingConfig, GenericTritonMapper


class ASRInferenceModel(InferenceModel):
    """ASR mapper-backed converter with audio context enrichment."""

    def __init__(
        self,
        model_name: str = "",
        endpoint_schema: Optional[Dict[str, Any]] = None,
        adapter_config: Optional[Union[AdapterMappingConfig, Dict[str, Any]]] = None,
    ):
        super().__init__(model_name=model_name, endpoint_schema=endpoint_schema)
        # Adapter config can come directly or from resolved endpoint metadata.
        config_payload = adapter_config or (endpoint_schema or {}).get("adapter_config")
        self.mapper: Optional[GenericTritonMapper] = (
            GenericTritonMapper(config_payload) if config_payload else None
        )

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[str]]:
        if not self.mapper:
            raise InferenceModelError("ASR adapter_config is not configured")
        # ASR adds derived audio context so configs can map audio.* fields
        # without hardcoding tensor assembly here.
        return self.mapper.render_inputs(
            input_data=input_data,
            config=config,
            context_builder=self._build_audio_context,
        )

    async def convert_triton_output_to_task_format(
        self,
        triton_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        if not self.mapper:
            raise InferenceModelError("ASR adapter_config is not configured")
        # Output mapping remains declaration-driven (maps_to roles).
        mapped = self.mapper.map_outputs(triton_output)
        return self.mapper.to_output_items(mapped)

    def _build_audio_context(
        self,
        item: Dict[str, Any],
        index: int,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        _ = index
        samples = item.get("samples")
        if samples is None:
            audio_content = item.get("audio_content")
            if audio_content:
                try:
                    # Minimal safe fallback: if decoded PCM samples are not prepared
                    # upstream, derive byte-level sequence from base64 payload.
                    raw = base64.b64decode(audio_content)
                    samples = list(raw)
                except Exception:
                    samples = []
            else:
                samples = []

        # Standardized context contract consumed by value_path declarations:
        # audio.samples, audio.num_samples, audio.sample_rate
        sample_rate = item.get("sample_rate") or config.get("sample_rate")
        return {
            "audio": {
                "samples": samples,
                "num_samples": item.get("num_samples", len(samples)),
                "sample_rate": sample_rate,
            }
        }
