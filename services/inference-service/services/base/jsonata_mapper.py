"""v2 adapter-config mapping via JSONata (AI4IDS-1981).

The v2 schema replaces the v1 declarative output pipeline (map_outputs,
to_output_items, shape_output_items, build_response_envelope) with one JSONata
expression that maps decoded Triton tensors to the final task-type output.

Two kinds of v2 service:
- config-only: declare `output_transform`; the base pipeline runs it.
- code-output (NER, TTS): omit `output_transform` and override produce_result,
  reading decoded tensors via V2Mapper.decode() and running their algorithm/DSP.

Input rendering stays the v1 typed path (dtype / shape / KServe v2 with
value_path), so a v2 config reuses GenericTritonMapper for inputs. JSON-blob
tensors are parsed by the mapper (per-output `is_json`) before evaluation.

`build_mapper` dispatches on `schema_version`: v2 -> V2Mapper, else v1.
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
    """A Triton output tensor to request and optionally JSON-parse (decode-level
    only; shaping lives in output_transform or in service code)."""

    tensor: str = Field(..., description="Tensor name returned by Triton")
    is_json: bool = Field(
        default=False,
        description="Parse this tensor's decoded string value as a JSON blob.",
    )


class AdapterMappingConfigV2(BaseModel):
    """v2 adapter mapping contract: typed inputs + optional output expression."""

    schema_version: str = Field(..., description="Adapter schema version, e.g. '2.0'")
    model_version: str = Field(default="1", description="Triton model version")
    inputs: List[InputTensorDeclaration] = Field(..., min_length=1)
    outputs: List[OutputTensorV2] = Field(..., min_length=1)
    output_transform: Optional[str] = Field(
        default=None,
        description="JSONata expression mapping decoded tensors to the final "
        "task-type output. Omitted for code-output services (NER, TTS) that "
        "override produce_result and consume V2Mapper.decode() directly.",
    )


# ── Decode helpers (Triton KServe v2 response -> native tensors) ────────────────

def _decode(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, list):
        return [_decode(item) for item in value]
    return value


def _parse_json(value: Any) -> Any:
    if isinstance(value, list):
        return [_parse_json(item) for item in value]
    if isinstance(value, str):
        stripped = value.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
    return value


def decode_triton_outputs(triton_output: Dict[str, Any], json_tensors) -> Dict[str, Any]:
    """Map a KServe v2 response to {tensor_name: data}; bytes decoded, declared
    json tensors parsed."""
    tensors: Dict[str, Any] = {}
    for output in triton_output.get("outputs", []):
        name = output.get("name")
        if name is None:
            continue
        data = _decode(output.get("data"))
        if name in json_tensors:
            data = _parse_json(data)
        tensors[name] = data
    return tensors


def decode_and_merge(raw_outputs: List[Dict[str, Any]], json_tensors) -> Dict[str, Any]:
    """Decode each Triton response and concatenate each tensor's data across
    calls, so batch (one call) and per-item (one per input) both yield
    `tensors.<NAME>` as the full array."""
    merged: Dict[str, Any] = {}
    for raw in raw_outputs:
        for name, data in decode_triton_outputs(raw, json_tensors).items():
            merged.setdefault(name, []).extend(data if isinstance(data, list) else [data])
    return merged


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
        return decode_triton_outputs(triton_output, self._json_tensors)

    def transform_output(
        self,
        tensors: Dict[str, Any],
        inputs: List[Dict[str, Any]],
        request_config: Optional[Dict[str, Any]],
    ) -> Any:
        return self._expr.evaluate({
            "tensors": tensors,
            "inputs": inputs or [],
            "request": {"config": request_config or {}},
        })


class V2Mapper:
    """A v2 mapper: v1 typed input rendering + JSONata output transform (or, for
    code-output services, decode() for the service to consume).

    Presents `compose_triton_kserve_v2_payload` (same as the v1 mapper) so the
    input hook is unchanged. Built per request, so any compiled JSONata
    expression is never shared across threads.
    """

    def __init__(self, adapter_config: Union[AdapterMappingConfigV2, Dict[str, Any]]):
        cfg = (
            adapter_config
            if isinstance(adapter_config, AdapterMappingConfigV2)
            else AdapterMappingConfigV2.model_validate(adapter_config)
        )
        self.adapter_config = cfg
        self._json_tensors = {o.tensor for o in cfg.outputs if o.is_json}
        self._jsonata = (
            JsonataOutputMapper(cfg.output_transform, list(self._json_tensors))
            if cfg.output_transform else None
        )

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

    def decode(self, raw_outputs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Decoded + merged tensors keyed by tensor name. Used by the JSONata
        transform and by code-output services (NER, TTS)."""
        return decode_and_merge(raw_outputs, self._json_tensors)

    def transform(
        self,
        raw_outputs: List[Dict[str, Any]],
        inputs: List[Dict[str, Any]],
        request_config: Optional[Dict[str, Any]],
    ) -> Any:
        if self._jsonata is None:
            raise RuntimeError(
                "V2Mapper.transform called but adapter_config has no output_transform"
            )
        return self._jsonata.transform_output(
            self.decode(raw_outputs), inputs, request_config
        )


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
