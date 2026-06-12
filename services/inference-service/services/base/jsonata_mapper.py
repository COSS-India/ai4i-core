"""Adapter-config mapping: typed Triton inputs + JSONata output transform.

One mapper per request, built from the model's adapter_config:
  inputs           — typed declarations rendered by TritonInputRenderer.
  outputs          — Triton output tensors to request (and optionally JSON-parse).
  output_transform — a JSONata expression mapping decoded tensors to the final
                     task-type output. Omitted for code-output services (NER,
                     TTS), which override produce_result and read decode()
                     directly to run their algorithm/DSP.

Input rendering is typed (a JSON engine cannot type or shape tensors); the
output path is JSONata. There is a single schema and a single mapper — the
earlier v1 declarative output pipeline has been removed.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from jsonata.jsonata import Jsonata

from services.base.config_mapper import InputTensorDeclaration, TritonInputRenderer


class OutputTensorDeclaration(BaseModel):
    """A Triton output tensor to request and optionally JSON-parse (decode-level
    only; shaping lives in output_transform or in service code)."""

    tensor: str = Field(..., description="Tensor name returned by Triton")
    is_json: bool = Field(
        default=False,
        description="Parse this tensor's decoded string value as a JSON blob.",
    )


class AdapterMappingConfig(BaseModel):
    """Adapter mapping contract: typed inputs + optional output expression."""

    schema_version: str = Field(..., description="Adapter schema version, e.g. '2.0'")
    model_version: str = Field(default="1", description="Triton model version")
    inputs: List[InputTensorDeclaration] = Field(..., min_length=1)
    outputs: List[OutputTensorDeclaration] = Field(..., min_length=1)
    output_transform: Optional[str] = Field(
        default=None,
        description="JSONata expression mapping decoded tensors to the final "
        "task-type output. Omitted for code-output services (NER, TTS) that "
        "override produce_result and consume decode() directly.",
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
    """Compiles an output_transform once and evaluates it per request.

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


class TritonMapper:
    """Per-request mapper: typed input rendering + JSONata output transform (or,
    for code-output services, decode() for the service to consume).

    Presents `compose_triton_kserve_v2_payload` so the input hook is uniform.
    Built per request, so any compiled JSONata expression is never shared
    across threads.
    """

    def __init__(self, adapter_config: Union[AdapterMappingConfig, Dict[str, Any]]):
        cfg = (
            adapter_config
            if isinstance(adapter_config, AdapterMappingConfig)
            else AdapterMappingConfig.model_validate(adapter_config)
        )
        self.adapter_config = cfg
        self._output_names = [o.tensor for o in cfg.outputs]
        self._json_tensors = {o.tensor for o in cfg.outputs if o.is_json}
        self._renderer = TritonInputRenderer(cfg.inputs)
        self._jsonata = (
            JsonataOutputMapper(cfg.output_transform, list(self._json_tensors))
            if cfg.output_transform else None
        )

    def compose_triton_kserve_v2_payload(self, input_data, config):
        inputs_list = self._renderer.compose_triton_kserve_v2_payload(
            input_data=input_data, config=config
        )
        return inputs_list, list(self._output_names)

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
                "TritonMapper.transform called but adapter_config has no output_transform"
            )
        return self._jsonata.transform_output(
            self.decode(raw_outputs), inputs, request_config
        )


def build_mapper(adapter_config: Dict[str, Any]) -> TritonMapper:
    """Build the per-request mapper for a model's adapter_config."""
    return TritonMapper(adapter_config)
