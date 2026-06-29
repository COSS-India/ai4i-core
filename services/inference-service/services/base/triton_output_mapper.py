"""Triton output mapping: decode KServe v2 responses + JSONata transform.

Built per request from the model's adapter_config (see adapter_config.py):
  outputs          — the Triton output tensors to request and (optionally)
                     JSON-parse.
  output_transform — a JSONata expression mapping the decoded tensors to the
                     final task-type output. Omitted for code-output services
                     (NER, TTS), which build their output in post_process from
                     decode() / the raw responses.

Owns the output side end to end: which tensors to request, how to decode them,
and the transform. The input side is TritonInputMapper (triton_input_mapper.py).
A JSON engine cannot type or shape input tensors, which is why the two
directions are separate mappers rather than one symmetric transform.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

from jsonata.jsonata import Jsonata
from pydantic import BaseModel, Field


class OutputTensorDeclaration(BaseModel):
    """A Triton output tensor to request and optionally JSON-parse (decode-level
    only; shaping lives in output_transform or in service code)."""

    tensor: str = Field(..., description="Tensor name returned by Triton")
    is_json: bool = Field(
        default=False,
        description="Parse this tensor's decoded string value as a JSON blob.",
    )


class TritonOutputMapper:
    """Per-request output mapper: names the output tensors to request, decodes
    the KServe v2 responses, and runs the adapter_config's output_transform
    (JSONata) over the decoded tensors.

    Compiles (and thereby syntax-validates) output_transform at construction, so
    an invalid expression fails at config load, not at inference time. Built per
    request, so the compiled expression is never shared across threads.
    """

    def __init__(
        self,
        outputs: Sequence[OutputTensorDeclaration],
        output_transform: Optional[str] = None,
    ):
        self._output_names = [o.tensor for o in outputs]
        self._json_tensors = {o.tensor for o in outputs if o.is_json}
        if output_transform:
            try:
                self._expr = Jsonata.jsonata(output_transform)
            except Exception as exc:
                raise RuntimeError(
                    f"Invalid output_transform JSONata expression: {exc}"
                ) from exc
        else:
            self._expr = None

    @property
    def output_names(self) -> List[str]:
        """Triton output tensor names to request in the inference call."""
        return list(self._output_names)

    @property
    def has_transform(self) -> bool:
        """True when an output_transform is declared (config-expressible
        service). False for code-output services (NER, TTS) that build their
        output in post_process."""
        return self._expr is not None

    # ── Decode (KServe v2 response -> native tensors) ───────────────────────

    @staticmethod
    def _decode(value: Any) -> Any:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if isinstance(value, list):
            return [TritonOutputMapper._decode(item) for item in value]
        return value

    @staticmethod
    def _parse_json(value: Any) -> Any:
        if isinstance(value, list):
            return [TritonOutputMapper._parse_json(item) for item in value]
        if isinstance(value, str):
            stripped = value.lstrip()
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
        return value

    def _decode_response(self, triton_output: Dict[str, Any]) -> Dict[str, Any]:
        """Map one KServe v2 response to {tensor_name: data}; bytes decoded,
        declared json tensors parsed."""
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

    def decode(self, raw_outputs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Decode each Triton response and concatenate each tensor's data across
        calls, so batch (one call) and per-item (one per input) both yield
        `tensors.<NAME>` as the full array. Consumed by the transform and by
        code-output services (NER, TTS)."""
        merged: Dict[str, Any] = {}
        for raw in raw_outputs:
            for name, data in self._decode_response(raw).items():
                merged.setdefault(name, []).extend(
                    data if isinstance(data, list) else [data]
                )
        return merged

    # ── Transform (decoded tensors -> final task-type output) ───────────────

    def transform(
        self,
        decoded: Dict[str, Any],
        inputs: List[Dict[str, Any]],
        request_config: Optional[Dict[str, Any]],
    ) -> Any:
        """Run the output_transform over already-decoded tensors (decoded once in
        run_inference, so the JSONata path never decodes a second time)."""
        if self._expr is None:
            raise RuntimeError(
                "TritonOutputMapper.transform called but adapter_config has no output_transform"
            )
        return self._expr.evaluate({
            "tensors": decoded,
            "inputs": inputs or [],
            "request": {"config": request_config or {}},
        })
