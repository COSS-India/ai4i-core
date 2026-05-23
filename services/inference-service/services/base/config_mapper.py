"""Generic adapter config declarations and path-based mapper utilities."""

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from pydantic import BaseModel, Field, model_validator


SUPPORTED_TRITON_DTYPES = {
    "BOOL",
    "BYTES",
    "FP16",
    "FP32",
    "FP64",
    "INT8",
    "INT16",
    "INT32",
    "INT64",
    "UINT8",
    "UINT16",
    "UINT32",
    "UINT64",
}


class GenericMapperError(Exception):
    """Base exception for generic mapper failures."""


class InputTensorDeclaration(BaseModel):
    """Input tensor declaration for adapter config."""

    tensor: str = Field(..., description="Tensor name expected by Triton model")
    dtype: str = Field(..., description="Triton dtype")
    shape: List[int] = Field(..., description="Tensor shape, -1 for dynamic dimension")
    value_path: Optional[str] = Field(
        default=None,
        description="Dot path from context (example: input.source or request.config.language.sourceLanguage)",
    )
    value: Optional[Any] = Field(
        default=None,
        description="Static value fallback. If string and value_path is absent, treated as value_path.",
    )

    @model_validator(mode="after")
    def normalize_value_fields(self) -> "InputTensorDeclaration":
        # Backward-compatible shorthand:
        # if adopters pass {"value": "input.source"}, treat it as value_path.
        if not self.value_path and isinstance(self.value, str):
            self.value_path = self.value
            self.value = None
        return self


class OutputTensorDeclaration(BaseModel):
    """Output tensor declaration for adapter config."""

    tensor: str = Field(..., description="Tensor name returned by Triton")
    dtype: str = Field(..., description="Expected Triton dtype")
    maps_to: str = Field(..., description="Platform semantic output key")


class AdapterMappingConfig(BaseModel):
    """Top-level adapter mapping contract."""

    version: str = Field(..., description="Schema version")
    model_version: str = Field(default="1", description="Triton model version")
    inputs: List[InputTensorDeclaration] = Field(..., min_items=1)
    outputs: List[OutputTensorDeclaration] = Field(..., min_items=1)


ContextBuilder = Callable[[Dict[str, Any], int, Dict[str, Any]], Dict[str, Any]]


class GenericTritonMapper:
    """Generic mapper that resolves Triton inputs and maps Triton outputs."""

    def __init__(self, adapter_config: Union[AdapterMappingConfig, Dict[str, Any]]):
        self.adapter_config = (
            adapter_config
            if isinstance(adapter_config, AdapterMappingConfig)
            else AdapterMappingConfig.parse_obj(adapter_config)
        )
        self._validate_config(self.adapter_config)

    def render_inputs(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
        context_builder: Optional[ContextBuilder] = None,
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Render adapter input declarations into Triton input payload.

        This keeps runtime deterministic:
        - no model-specific branching
        - only declared paths/static values are used
        """
        if not input_data:
            raise GenericMapperError("input_data cannot be empty")

        triton_inputs: Dict[str, Any] = {}
        for tensor_cfg in self.adapter_config.inputs:
            rendered_values: List[Any] = []
            for index, item in enumerate(input_data):
                # Canonical context available for every tensor declaration.
                context: Dict[str, Any] = {
                    "request": {"config": config},
                    "input": item,
                    "index": index,
                }
                if context_builder:
                    # Task-specific enrichments (for example audio.samples)
                    # are merged without changing generic mapper logic.
                    context.update(context_builder(item, index, config) or {})

                resolved = self._resolve_value(tensor_cfg=tensor_cfg, context=context)
                rendered_values.append(self._cast_dtype(resolved, tensor_cfg.dtype))

            # Keep Triton payload shape explicit per declaration.
            shape, data = self._materialize_tensor(rendered_values, tensor_cfg.shape, tensor_cfg.dtype)
            triton_inputs[tensor_cfg.tensor] = {
                "dtype": tensor_cfg.dtype,
                "shape": shape,
                "data": data,
            }

        output_names = [output.tensor for output in self.adapter_config.outputs]
        return triton_inputs, output_names

    def compose_triton_kserve_v2_payload(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
        context_builder: Optional[ContextBuilder] = None,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Render inputs and return a KServe v2 ready inputs list paired with output names.

        Returns:
            Tuple of (inputs_list, output_names) where inputs_list entries use
            'datatype' (KServe v2 wire field) instead of the internal 'dtype'.
        """
        triton_inputs, output_names = self.render_inputs(input_data, config, context_builder)
        inputs_list = [
            {"name": name, "datatype": t["dtype"], "shape": t["shape"], "data": t["data"]}
            for name, t in triton_inputs.items()
        ]
        return inputs_list, output_names

    def map_outputs(self, triton_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map Triton outputs to semantic keys based on adapter declarations.

        Example: OUTPUT_TEXT -> translated_text
        """
        mapped: Dict[str, Any] = {}
        for output_cfg in self.adapter_config.outputs:
            value = self._extract_output_tensor(triton_output, output_cfg.tensor)
            if value is None:
                raise GenericMapperError(f"Missing output tensor '{output_cfg.tensor}'")
            mapped[output_cfg.maps_to] = self._decode_output_value(value)
        return mapped

    def to_output_items(self, mapped_outputs: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert mapped outputs into task-service friendly list-of-dict items."""
        batch_size = 1
        for value in mapped_outputs.values():
            if isinstance(value, list) and value:
                batch_size = max(batch_size, len(value))

        items: List[Dict[str, Any]] = []
        for idx in range(batch_size):
            item: Dict[str, Any] = {}
            for key, value in mapped_outputs.items():
                if isinstance(value, list):
                    item[key] = value[idx] if idx < len(value) else value[-1]
                else:
                    item[key] = value
            items.append(item)
        return items

    # ------------------------------------------------------------------
    # BaseTaskService interface — execute_triton_inference calls these
    # ------------------------------------------------------------------

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Convert task input + config into KServe v2 Triton payload."""
        return self.compose_triton_kserve_v2_payload(input_data, config)

    async def convert_triton_output_to_task_format(
        self,
        triton_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Map Triton tensor output to a list-of-dict task response items."""
        return self.to_output_items(self.map_outputs(triton_output))

    def _validate_config(self, config: AdapterMappingConfig) -> None:
        if not config.version.strip():
            raise GenericMapperError("adapter config version cannot be empty")

        for tensor in config.inputs:
            if tensor.dtype not in SUPPORTED_TRITON_DTYPES:
                raise GenericMapperError(f"Unsupported input dtype '{tensor.dtype}'")
            if not tensor.shape:
                raise GenericMapperError(f"Input tensor '{tensor.tensor}' shape cannot be empty")
            if tensor.value_path is None and tensor.value is None:
                raise GenericMapperError(
                    f"Input tensor '{tensor.tensor}' requires value_path or value"
                )

        for tensor in config.outputs:
            if tensor.dtype not in SUPPORTED_TRITON_DTYPES:
                raise GenericMapperError(f"Unsupported output dtype '{tensor.dtype}'")
            if not tensor.maps_to.strip():
                raise GenericMapperError(f"Output tensor '{tensor.tensor}' maps_to cannot be empty")

    def _resolve_value(
        self,
        tensor_cfg: InputTensorDeclaration,
        context: Dict[str, Any],
    ) -> Any:
        if tensor_cfg.value_path:
            return self._resolve_path(context, tensor_cfg.value_path)
        return tensor_cfg.value

    def _resolve_path(self, source: Any, path: str) -> Any:
        # Dot-path walker for config-driven lookup.
        # Supports dict keys and object attributes.
        current = source
        for part in path.split("."):
            if isinstance(current, dict):
                if part not in current:
                    raise GenericMapperError(f"Path '{path}' not found (missing key '{part}')")
                current = current[part]
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                raise GenericMapperError(f"Path '{path}' not found at '{part}'")
        return current

    def _cast_dtype(self, value: Any, dtype: str) -> Any:
        if isinstance(value, list):
            return [self._cast_dtype(item, dtype) for item in value]
        if dtype.startswith("FP"):
            return float(value)
        if dtype.startswith("INT") or dtype.startswith("UINT"):
            return int(value)
        if dtype == "BOOL":
            return bool(value)
        if dtype == "BYTES":
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="replace")
            return str(value)
        return value

    def _materialize_tensor(
        self,
        rendered_values: List[Any],
        declared_shape: Sequence[int],
        dtype: str,
    ) -> Tuple[List[int], List[Any]]:
        # Normalize per-item values into a single declared tensor payload.
        normalized: Any = rendered_values
        if len(declared_shape) > 1:
            normalized = [value if isinstance(value, list) else [value] for value in rendered_values]
        inferred_shape = self._infer_shape(normalized)
        final_shape = self._apply_declared_shape(inferred_shape, list(declared_shape))
        flattened = self._flatten(normalized)
        casted = [self._cast_dtype(item, dtype) for item in flattened]
        return final_shape, casted

    def _infer_shape(self, value: Any) -> List[int]:
        if not isinstance(value, list):
            return []
        if not value:
            return [0]
        return [len(value)] + self._infer_shape(value[0])

    def _apply_declared_shape(self, inferred: List[int], declared: List[int]) -> List[int]:
        if len(inferred) < len(declared):
            inferred = inferred + [1] * (len(declared) - len(inferred))
        elif len(inferred) > len(declared):
            raise GenericMapperError(
                f"Declared shape {declared} has fewer dims than inferred shape {inferred}"
            )

        resolved: List[int] = []
        for expected, actual in zip(declared, inferred):
            if expected == -1:
                resolved.append(actual)
            elif expected == actual:
                resolved.append(actual)
            else:
                raise GenericMapperError(
                    f"Declared shape {declared} does not match inferred shape {inferred}"
                )
        return resolved

    def _flatten(self, value: Any) -> List[Any]:
        if not isinstance(value, list):
            return [value]
        flattened: List[Any] = []
        for item in value:
            flattened.extend(self._flatten(item))
        return flattened

    def _extract_output_tensor(self, triton_output: Dict[str, Any], tensor_name: str) -> Any:
        outputs = triton_output.get("outputs")
        if isinstance(outputs, list):
            for output in outputs:
                if output.get("name") == tensor_name:
                    return output.get("data")
        return triton_output.get(tensor_name)

    def _decode_output_value(self, value: Any) -> Any:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if isinstance(value, list):
            return [self._decode_output_value(item) for item in value]
        return value
