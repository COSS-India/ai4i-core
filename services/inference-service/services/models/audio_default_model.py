"""
AudioDefaultModel — shared audio model for tasks that send raw audio to Triton.

Used by tasks where Triton handles audio decoding internally: ALD,
Speaker Diarization, Language Diarization. These tasks skip float PCM
preprocessing and pass base64-encoded audio bytes directly.

Tasks that need float PCM preprocessing (ASR) extend AudioBase directly
and live in their own service file.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from services.base.audio_base import AudioBase
from services.base.config_mapper import GenericTritonMapper

logger = logging.getLogger(__name__)


class AudioDefaultModel(AudioBase):
    """
    Concrete audio model for base64-passthrough tasks.

    Overrides preprocess_input to skip float decode — audio is forwarded
    as base64 bytes directly to Triton. Tensor mapping in both directions
    is driven entirely by adapter_config via GenericTritonMapper.

    Can be registered directly in the task registry for any base64-passthrough
    audio task (ALD, Speaker Diarization, Language Diarization). Different tasks
    share this class; the adapter_config and Triton model name are what differ.

    Output is returned as a generic dict — the route layer applies
    GenericInferenceResponse, so no task-specific subclassing is needed.
    """

    def __init__(self, service_info: Optional[Dict[str, Any]] = None, **kwargs: Any):
        super().__init__(service_info=service_info, **kwargs)
        self.logger = logger

    # ------------------------------------------------------------------
    # Preprocessing — base64 passthrough
    # ------------------------------------------------------------------

    async def preprocess_input(self, input_data: List[Any]) -> List[Dict[str, Any]]:
        """
        No float decode. Each item is passed through as-is.
        If only audioUri is provided, downloads and base64-encodes it
        so convert_payload_to_triton_format always has audio_content.
        """
        if not input_data:
            raise ValueError(f"{self.task_name}: audio list cannot be empty")

        items = []
        for item in input_data:
            d = item if isinstance(item, dict) else item.model_dump(by_alias=False)
            has_content = d.get("audio_content") or d.get("audioContent")
            if not has_content:
                has_uri = d.get("audio_uri") or d.get("audioUri")
                if has_uri:
                    d = dict(d)
                    d["audio_content"] = await self._resolve_audio_base64(item)
            items.append(d)
        return items

    # ------------------------------------------------------------------
    # Triton format hooks — adapter_config driven
    # ------------------------------------------------------------------

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Build Triton inputs from adapter_config tensor declarations."""
        config = dict(config)
        if "num_speakers" not in config and "numSpeakers" not in config:
            config["num_speakers"] = ""
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
        """Map Triton output tensors to result dicts via adapter_config."""
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
        Context for adapter_config value_path resolution.
        Exposes audio.audio_content — the base64 string passed to Triton.
        """
        audio_content = item.get("audio_content") or item.get("audioContent") or ""
        return {
            "audio": {
                "audio_content": audio_content,
            }
        }

    # ------------------------------------------------------------------
    # Output — generic passthrough; route layer applies task-specific schema
    # ------------------------------------------------------------------

    async def postprocess_output(
        self, response_items: List[Dict[str, Any]], **kwargs: Any
    ) -> Dict[str, Any]:
        """Unwrap single-element nested lists and decode bytes in each output item.

        Triton KServe v2 returns tensors as flat lists (e.g. shape [1,1] → ["hi"]).
        After GenericTritonMapper processes them they may still be wrapped in a list.
        This ensures scalar values like language_code and confidence are plain
        Python scalars/strings rather than single-element lists.
        """
        unwrapped = []
        for item in response_items:
            clean = {}
            for key, value in item.items():
                while isinstance(value, (list, tuple)) and len(value) == 1:
                    value = value[0]
                if isinstance(value, bytes):
                    value = value.decode("utf-8", errors="replace")
                if key == "all_scores" and isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except (json.JSONDecodeError, ValueError):
                        pass
                if key == "confidence":
                    try:
                        value = float(value)
                    except (TypeError, ValueError):
                        pass
                clean[key] = value
            unwrapped.append(clean)
        return {"output": unwrapped}

    def _build_response(
        self, payload: Dict[str, Any], postprocessed: Dict[str, Any]
    ) -> Dict[str, Any]:
        cfg = payload.get("config") or {}
        return {
            "taskType": "audio-lang-detection",
            "output": postprocessed["output"],
            "config": {"serviceId": cfg.get("serviceId")},
        }
