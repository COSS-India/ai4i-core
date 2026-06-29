"""Typed Triton input mapping for adapter configs.

The adapter config declares each Triton input tensor (name, dtype, shape, and a
value_path into the request; see adapter_config.py). TritonInputMapper walks
those declarations and builds a KServe v2 input payload. This is the ONLY input
transform: tensors are typed and shaped, which a JSON-to-JSON engine cannot
express, so the input path stays declarative here and the output path is JSONata
(see triton_output_mapper.py).

value_path namespaces:
  request.*  — the request envelope, wire casing (camelCase, e.g.
               request.config.language.sourceLanguage).
  input.*    — the current input item, including any fields preprocessing wrote
               onto it (input.source, input.audioContent, ASR's input.samples,
               TTS's input.gender).
  index      — the item's position in the batch.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple

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


class InputTensorDeclaration(BaseModel):
    """Input tensor declaration for adapter config."""

    tensor: str = Field(..., description="Tensor name expected by Triton model")
    dtype: str = Field(..., description="Triton dtype")
    shape: List[int] = Field(..., description="Tensor shape, -1 for dynamic dimension")
    value_path: Optional[str] = Field(
        default=None,
        description="Dot path from context (example: input.source or "
        "request.config.language.sourceLanguage)",
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


class TritonInputMapper:
    """Renders typed input-tensor declarations into a KServe v2 Triton payload.

    Constructed directly from the adapter config's input declarations. Owns the
    input side only; TritonOutputMapper owns decode + output transform.
    """

    def __init__(self, inputs: Sequence[InputTensorDeclaration]):
        self._inputs = list(inputs)
        self._validate()

    def _validate(self) -> None:
        if not self._inputs:
            raise RuntimeError("adapter config must declare at least one input tensor")
        for tensor in self._inputs:
            if tensor.dtype not in SUPPORTED_TRITON_DTYPES:
                raise RuntimeError(f"Unsupported input dtype '{tensor.dtype}'")
            if not tensor.shape:
                raise RuntimeError(f"Input tensor '{tensor.tensor}' shape cannot be empty")
            if tensor.value_path is None and tensor.value is None:
                raise RuntimeError(
                    f"Input tensor '{tensor.tensor}' requires value_path or value"
                )

    def compose_triton_kserve_v2_payload(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Render the declared inputs into a KServe v2 inputs list.

        Returns inputs_list entries using 'datatype' (the KServe v2 wire field).
        Output tensor names are owned by the caller (the mapper), not here.
        Each value_path resolves against {request, input, index}; service
        preprocessing writes any derived fields (e.g. ASR samples) onto the
        input item, so they are reachable as input.<field> with no extra hook.
        """
        if not input_data:
            raise RuntimeError("input_data cannot be empty")

        inputs_list: List[Dict[str, Any]] = []
        for tensor_cfg in self._inputs:
            rendered_values: List[Any] = []
            for index, item in enumerate(input_data):
                context: Dict[str, Any] = {
                    "request": {"config": config},
                    "input": item,
                    "index": index,
                }
                resolved = self._resolve_value(tensor_cfg, context)
                rendered_values.append(self._cast_dtype(resolved, tensor_cfg.dtype))

            shape, data = self._materialize_tensor(
                rendered_values, tensor_cfg.shape, tensor_cfg.dtype
            )
            inputs_list.append(
                {"name": tensor_cfg.tensor, "datatype": tensor_cfg.dtype, "shape": shape, "data": data}
            )
        return inputs_list

    # ------------------------------------------------------------------
    # Value resolution + tensor materialization
    # ------------------------------------------------------------------

    def _resolve_value(self, tensor_cfg: InputTensorDeclaration, context: Dict[str, Any]) -> Any:
        if tensor_cfg.value_path:
            try:
                return self._resolve_path(context, tensor_cfg.value_path)
            except RuntimeError:
                # A declaration may carry both value_path and a `value` default:
                # the path wins when present, the default applies when the key is
                # absent (e.g. optional config like numSpeakers/targetLanguage).
                if tensor_cfg.value is not None:
                    return tensor_cfg.value
                # No default: the request omitted a required input. That is a
                # client error (400), not a server fault — the typed declaration
                # IS the required-field check, so services need no validate hook.
                raise ValueError(
                    f"required input '{tensor_cfg.tensor}': "
                    f"'{tensor_cfg.value_path}' is missing from the request"
                ) from None
        return tensor_cfg.value

    def _resolve_path(self, source: Any, path: str) -> Any:
        """Dot-path walker over dicts and object attributes.

        Keys are matched exactly: the request envelope uses wire casing
        (camelCase) and internal namespaces (input./audio.) use their own keys,
        so no case-coercion is needed.
        """
        current = source
        for part in path.split("."):
            if isinstance(current, dict):
                if part not in current:
                    raise RuntimeError(f"Path '{path}' not found (missing key '{part}')")
                current = current[part]
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                raise RuntimeError(f"Path '{path}' not found at '{part}'")
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
        normalized: Any = rendered_values
        if len(declared_shape) > 1:
            normalized = [v if isinstance(v, list) else [v] for v in rendered_values]
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
            raise RuntimeError(
                f"Declared shape {declared} has fewer dims than inferred shape {inferred}"
            )

        resolved: List[int] = []
        for expected, actual in zip(declared, inferred):
            if expected == -1 or expected == actual:
                resolved.append(actual)
            else:
                raise RuntimeError(
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
