"""
Triton Client -- Generic inference client using httpx.

Usage:
    from ai4icore_model_management import TritonClient

    client = TritonClient(triton_url="<endpoint from services table>", api_key="...")
    result = client.send_triton_request("my_model", inputs, outputs)
    array = result.as_numpy("OUTPUT_NAME")

    # Or inherit for service-specific I/O
    class NERTritonClient(TritonClient):
        def get_ner_io(self, texts, language):
            ...
"""

import logging
import time
from contextvars import ContextVar
from typing import Dict, List, Optional, Union

import httpx
import numpy as np
from tritonclient.http import InferInput, InferRequestedOutput
from tritonclient.utils import (
    deserialize_bytes_tensor,
    np_to_triton_dtype,
    triton_to_np_dtype,
)

from ai4icore_exceptions import TritonInferenceError
from ai4icore_env import app_env

logger = logging.getLogger(__name__)

# Reference to the current ASGI scope dict, set by InferenceHeadersMiddleware.
# TritonClient accumulates inference timing into scope["_inference_model_time_ms"].
_current_scope: ContextVar[dict] = ContextVar("_current_scope", default=None)

SCOPE_KEY = "_inference_model_time_ms"


def _accumulate_inference_time(elapsed_ms: float) -> None:
    """Add elapsed_ms to the running total in the current request's ASGI scope."""
    scope = _current_scope.get()
    if scope is not None:
        scope[SCOPE_KEY] = scope.get(SCOPE_KEY, 0.0) + elapsed_ms
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode

    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False


# ------------------------------------------------------------------
# Response wrapper
# ------------------------------------------------------------------

class InferResult:
    """Lightweight wrapper over a Triton V2 JSON response."""

    __slots__ = ("_outputs",)

    def __init__(self, response_data: dict):
        self._outputs: Dict[str, dict] = {
            out["name"]: out for out in response_data.get("outputs", [])
        }

    def as_numpy(self, name: str) -> Optional[np.ndarray]:
        """Return the named output tensor as a numpy array (matches tritonclient API)."""
        output = self._outputs.get(name)
        if output is None:
            return None

        shape = output["shape"]
        datatype = output["datatype"]
        data = output.get("data")
        if data is None:
            return None

        flat = _flatten(data)

        if datatype == "BYTES":
            arr = np.array(
                [v.encode("utf-8") if isinstance(v, str) else v for v in flat],
                dtype=object,
            )
        else:
            arr = np.array(flat, dtype=triton_to_np_dtype(datatype))

        return arr.reshape(shape)


# ------------------------------------------------------------------
# Serialisation helpers
# ------------------------------------------------------------------

def _flatten(data) -> list:
    """Recursively flatten nested lists into a 1-D list."""
    if not isinstance(data, list):
        return [data]
    out: list = []
    for item in data:
        out.extend(_flatten(item))
    return out


def _serialize_input(inp: InferInput) -> dict:
    """Convert an *InferInput* to a Triton V2 JSON dict."""
    tensor: dict = {
        "name": inp.name(),
        "datatype": inp.datatype(),
        "shape": list(inp.shape()),
    }

    json_data = getattr(inp, "_data", None)
    if json_data is not None:
        tensor["data"] = json_data
        return tensor

    raw = getattr(inp, "_raw_data", None)
    if raw is not None:
        if inp.datatype() == "BYTES":
            byte_vals = deserialize_bytes_tensor(raw)
            tensor["data"] = [
                v.decode("utf-8") if isinstance(v, bytes) else str(v)
                for v in byte_vals
            ]
        else:
            tensor["data"] = np.frombuffer(
                raw, dtype=triton_to_np_dtype(inp.datatype())
            ).tolist()

    return tensor


# ------------------------------------------------------------------
# Client
# ------------------------------------------------------------------

class TritonClient:
    """Generic Triton inference client.

    Posts directly to the endpoint URL from the services table.
    No URL manipulation is performed -- the caller is expected to
    supply a valid, fully-qualified inference URL.
    """

    def __init__(
        self,
        triton_url: str,
        api_key: Optional[str] = None,
        timeout: int = 30,
    ):
        self.triton_url = triton_url.strip()
        self.api_key = api_key
        self.timeout = timeout
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        """Lazy-initialised httpx client."""
        if self._client is None:
            logger.info("Initializing Triton httpx client for: %s", self.triton_url)
            self._client = httpx.Client(timeout=self.timeout, verify=app_env.inference_ssl_verify)
        return self._client

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------
    def send_triton_request(
        self,
        model_name: str,
        inputs: List[InferInput],
        outputs: List[InferRequestedOutput],
        headers: Optional[Dict[str, str]] = None,
        model_version: str = "1",
        *,
        trace_attributes: Optional[Dict[str, Union[str, int, float, bool]]] = None,
    ) -> InferResult:
        """POST the inference payload directly to *self.triton_url*.

        *model_name* and *model_version* are retained for logging / tracing
        only -- they do **not** alter the URL.

        *trace_attributes*: optional extra attributes on the ``triton.inference`` span
        (e.g. batch loop index for multi-call phases).
        """
        start = time.perf_counter()
        try:
            if _OTEL_AVAILABLE:
                return self._send_traced(
                    model_name,
                    inputs,
                    outputs,
                    headers,
                    model_version,
                    trace_attributes,
                )
            return self._send_impl(model_name, inputs, outputs, headers, model_version)
        finally:
            _accumulate_inference_time((time.perf_counter() - start) * 1000)

    # -- traced wrapper ------------------------------------------------

    def _send_traced(
        self,
        model_name,
        inputs,
        outputs,
        headers,
        model_version,
        trace_attributes: Optional[Dict[str, Union[str, int, float, bool]]] = None,
    ):
        tracer = trace.get_tracer("ai4icore_model_management")
        with tracer.start_as_current_span("triton.inference") as span:
            span.set_attribute("triton.model_name", model_name)
            span.set_attribute("triton.endpoint", self.triton_url)
            span.set_attribute("triton.has_auth", bool(self.api_key))
            span.set_attribute("triton.input_count", len(inputs))
            span.set_attribute("triton.output_count", len(outputs))
            span.set_attribute("triton.timeout_seconds", self.timeout)
            span.set_attribute(
                "triton.input_tensor_names",
                ",".join(inp.name() for inp in inputs),
            )
            span.set_attribute(
                "triton.output_tensor_names",
                ",".join(out.name() for out in outputs),
            )
            if inputs:
                shape = inputs[0].shape()
                if shape:
                    span.set_attribute("triton.request_batch_size", int(shape[0]))
            span.set_attribute(
                "triton.phase",
                "http_post_infer_parse_response",
            )
            if trace_attributes:
                for attr_key, attr_val in trace_attributes.items():
                    if attr_val is None:
                        continue
                    try:
                        span.set_attribute(attr_key, attr_val)
                    except (TypeError, ValueError):
                        logger.debug(
                            "Skipping triton.inference attribute %s (unsupported type)",
                            attr_key,
                        )
            span.add_event(
                "triton.inference.start",
                {
                    "model": model_name,
                    "input_tensors": ",".join(inp.name() for inp in inputs),
                    "output_tensors": ",".join(out.name() for out in outputs),
                },
            )
            try:
                result = self._send_impl(model_name, inputs, outputs, headers, model_version)
                span.set_attribute("triton.status", "success")
                span.add_event("triton.inference.complete", {"status": "success"})
                return result
            except Exception as e:
                span.set_attribute("triton.status", "failed")
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    # -- core implementation -------------------------------------------

    def _build_infer_url(self, model_name: str, model_version: str) -> str:
        """Build the full Triton V2 infer URL.

        If triton_url already contains ``/v2/models/`` (full path), use as-is.
        Otherwise append ``/v2/models/{model_name}/versions/{model_version}/infer``.
        """
        url = self.triton_url.rstrip("/")
        if "/v2/models/" in url:
            return url
        return f"{url}/v2/models/{model_name}/versions/{model_version}/infer"

    def _send_impl(self, model_name, inputs, outputs, headers, model_version):
        try:
            req_headers = dict(headers or {})
            req_headers["Content-Type"] = "application/json"
            if self.api_key:
                req_headers["Authorization"] = f"Bearer {self.api_key}"

            payload = {
                "inputs": [_serialize_input(inp) for inp in inputs],
                "outputs": [{"name": out.name()} for out in outputs],
            }

            infer_url = self._build_infer_url(model_name, model_version)
            logger.debug(
                "Triton inference: model='%s' endpoint='%s'", model_name, infer_url
            )

            response = self.client.post(infer_url, json=payload, headers=req_headers)
            response.raise_for_status()
            return InferResult(response.json())

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            logger.error(
                "Triton inference failed: model='%s' endpoint='%s' status=%s",
                model_name, self.triton_url, status,
            )
            if status == 404:
                raise TritonInferenceError(
                    f"Model '{model_name}' not found at '{self.triton_url}'.",
                    model_name=model_name,
                ) from e
            raise TritonInferenceError(
                f"Triton inference failed ({status}): {e}", model_name=model_name
            ) from e

        except httpx.ConnectError as e:
            logger.error("Cannot connect to Triton at '%s': %s", self.triton_url, e)
            raise TritonInferenceError(
                f"Cannot connect to Triton at '{self.triton_url}'. "
                "Verify endpoint and server status.",
                model_name=model_name,
            ) from e

        except Exception as e:
            logger.error(
                "Triton inference failed: model='%s' endpoint='%s' error=%s",
                model_name, self.triton_url, e,
            )
            raise TritonInferenceError(
                f"Triton inference failed: {e}", model_name=model_name
            ) from e

    # ------------------------------------------------------------------
    # Tensor helpers (used by service-specific subclasses)
    # ------------------------------------------------------------------
    def _get_string_tensor(self, string_values: List[str], tensor_name: str) -> InferInput:
        """Create a BYTES tensor with shape [batch, 1]."""
        try:
            nested = [[v] for v in string_values]
            np_array = np.array(nested, dtype=object)
            tensor = InferInput(tensor_name, list(np_array.shape), np_to_triton_dtype(np_array.dtype))
            tensor.set_data_from_numpy(np_array)
            return tensor
        except Exception as e:
            raise TritonInferenceError(f"Failed to create tensor '{tensor_name}': {e}") from e

    def _get_bool_tensor(self, bool_values: List[bool], tensor_name: str) -> InferInput:
        """Create a BOOL tensor with shape [batch, 1]."""
        try:
            nested = [[v] for v in bool_values]
            np_array = np.array(nested, dtype=bool)
            tensor = InferInput(tensor_name, list(np_array.shape), np_to_triton_dtype(np_array.dtype))
            tensor.set_data_from_numpy(np_array)
            return tensor
        except Exception as e:
            raise TritonInferenceError(f"Failed to create tensor '{tensor_name}': {e}") from e
