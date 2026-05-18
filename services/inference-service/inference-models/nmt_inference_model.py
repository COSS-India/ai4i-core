"""NMT (Neural Machine Translation) InferenceModel using generic mapper."""

from typing import Any, Dict, List, Optional, Tuple, Union

from inference_models.base_inference_model import InferenceModel, InferenceModelError
from inference_models.config_mapper import AdapterMappingConfig, GenericTritonMapper


class NMTInferenceModel(InferenceModel):
    """NMT mapper-backed converter."""

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
            raise InferenceModelError("NMT adapter_config is not configured")
        # NMT uses only standard request/input paths; no extra context hook needed.
        return self.mapper.render_inputs(input_data=input_data, config=config)

    async def convert_triton_output_to_task_format(
        self,
        triton_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        if not self.mapper:
            raise InferenceModelError("NMT adapter_config is not configured")
        # Generic role mapping keeps response shape model-agnostic.
        mapped = self.mapper.map_outputs(triton_output)
        return self.mapper.to_output_items(mapped)
