"""v2 adapter-config mapping via JSONata (AI4IDS-1981).

The v2 schema replaces the v1 declarative output pipeline (map_outputs,
to_output_items, shape_output_items, build_response_envelope) with one JSONata
expression that maps decoded Triton tensors to the final task-type output.

Scope: the output side. Input rendering stays the v1 typed path (dtype / shape /
KServe v2 materialization with value_path), so a v2 config reuses
GenericTritonMapper for inputs and differs only on output. `V2Mapper` wraps both
sides behind the same surface the task pipeline already calls.

JSON-blob tensors (e.g. a diarization result) are parsed by the mapper before
evaluation, declared via the per-output `json` flag, so expressions operate on
native objects and need no custom JSONata functions.

`build_mapper` dispatches on `schema_version`: v2 configs get a `V2Mapper`,
everything else the v1 `GenericTritonMapper`.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from jsonata.jsonata import Jsonata

from services.base.config_mapper import (
    AdapterMappingConfig,
    GenericTritonMapper,
    InputTensorDeclaration,
    OutputTensorDeclaration,
)


class OutputTensorV2(BaseModel):
    """A Triton output tensor to request and optionally JSON-parse. Decode-level
    only: the shaping lives entirely in output_transform."""

    tensor: str = Field(..., description="Tensor name returned by Triton")
    is_json: bool = Field(
        default=False,
        description="Parse this tensor's decoded string value as a JSON blob "
        "before the transform runs.",
    )


class AdapterMappingConfigV2(BaseModel):
    """v2 adapter mapping contract: typed inputs + one output expression."""

    schema_version: str = Field(..., description="Adapter schema version, e.g. '2.0'")
    model_version: str = Field(default="1", description="Triton model version")
    inputs: List[InputTensorDeclaration] = Field(..., min_length=1)
    outputs: List[OutputTensorV2] = Field(..., min_length=1)
    output_transform: str = Field(
        ...,
        min_length=1,
        description="JSONata expression mapping decoded tensors to the final "
        "task-type output. Context: {tensors, inputs, request:{config}}.",
    )


class JsonataOutputMapper:
    """Compiles a v2 output_transform once and evaluates it per request.

    Construction compiles (and thereby syntax-validates) the expression, so an
    invalid expression fails at config load, not at inference time.
    """

    def __init__(self, output_transform: str, json_tensors: Optional[List[str]] = None):
        self._json_tensors = set(json_tensors or [])
        try:
            self._expr = Jsonata.jsonata(output_transform)
        except Exception as exc:
            raise RuntimeError(
                f"Invalid output_transform JSONata expression: {exc}"
            ) from exc

    def decode_triton_outputs(self, triton_output: Dict[str, Any]) -> Dict[str, Any]:
        """Build the `tensors` map keyed by tensor name from a KServe v2 response.

        Bytes are decoded to str; tensors flagged `json` have each string element
        parsed. Values stay as the tensor's data list; the expression handles
        indexing and flattening.
        """
        tensors: Dict[str, Any] = {}
        for output in triton_output.get("outputs", []):
            name = output.get("name")
            if name is None:
                continue
            data = self._decode(output.get("data"))
            if name in self._json_tensors:
                data = self._parse_json(data)
            tensors[name] = data
        return tensors

    def transform_output(
        self,
        tensors: Dict[str, Any],
        inputs: List[Dict[str, Any]],
        request_config: Optional[Dict[str, Any]],
    ) -> Any:
        """Evaluate the output_transform over the standard v2 context."""
        context = {
            "tensors": tensors,
            "inputs": inputs or [],
            "request": {"config": request_config or {}},
        }
        return self._expr.evaluate(context)

    def _decode(self, value: Any) -> Any:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if isinstance(value, list):
            return [self._decode(item) for item in value]
        return value

    def _parse_json(self, value: Any) -> Any:
        if isinstance(value, list):
            return [self._parse_json(item) for item in value]
        if isinstance(value, str):
            stripped = value.lstrip()
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
        return value


class V2Mapper:
    """A v2 mapper: v1 typed input rendering + JSONata output transform.

    Presents `compose_triton_kserve_v2_payload` (same as the v1 mapper) so the
    task pipeline's input hook is unchanged, plus `transform` for the output.
    Built per request, so its compiled JSONata expression is never shared across
    threads.
    """

    def __init__(self, adapter_config: Union[AdapterMappingConfigV2, Dict[str, Any]]):
        cfg = (
            adapter_config
            if isinstance(adapter_config, AdapterMappingConfigV2)
            else AdapterMappingConfigV2.model_validate(adapter_config)
        )
        self.adapter_config = cfg
        json_tensors = [o.tensor for o in cfg.outputs if o.is_json]
        self._output = JsonataOutputMapper(cfg.output_transform, json_tensors)

        # Reuse the v1 input renderer: synthesize a v1 config from the typed
        # inputs plus the output tensor names (so Triton is asked for them).
        input_cfg = AdapterMappingConfig(
            version=cfg.schema_version,
            model_version=cfg.model_version,
            inputs=cfg.inputs,
            outputs=[
                OutputTensorDeclaration(tensor=o.tensor, dtype="BYTES", maps_to=o.tensor)
                for o in cfg.outputs
            ],
        )
        self._input_mapper = GenericTritonMapper(input_cfg)

    def compose_triton_kserve_v2_payload(self, input_data, config, context_builder=None):
        return self._input_mapper.compose_triton_kserve_v2_payload(
            input_data=input_data, config=config, context_builder=context_builder
        )

    def transform(
        self,
        raw_outputs: List[Dict[str, Any]],
        inputs: List[Dict[str, Any]],
        request_config: Optional[Dict[str, Any]],
    ) -> Any:
        """Decode and merge tensors across all Triton calls, then transform once.

        Merging concatenates each call's tensor data, so batch (one call) and
        per-item (one call per input) modes both yield `tensors.<NAME>` as the
        full array the expression maps over.
        """
        merged: Dict[str, Any] = {}
        for raw in raw_outputs:
            tensors = self._output.decode_triton_outputs(raw)
            for name, data in tensors.items():
                bucket = merged.setdefault(name, [])
                bucket.extend(data if isinstance(data, list) else [data])
        return self._output.transform_output(merged, inputs, request_config)


def is_v2_config(adapter_config: Any) -> bool:
    """True if the adapter_config declares the v2 (JSONata) schema."""
    return (
        isinstance(adapter_config, dict)
        and str(adapter_config.get("schema_version", "")).startswith("2")
    )


def build_mapper(adapter_config: Dict[str, Any]) -> Union[GenericTritonMapper, V2Mapper]:
    """Return the mapper for an adapter_config: v2 -> V2Mapper, else v1."""
    if is_v2_config(adapter_config):
        return V2Mapper(adapter_config)
    return GenericTritonMapper(adapter_config)
