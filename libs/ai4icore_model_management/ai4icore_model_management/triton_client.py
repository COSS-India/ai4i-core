"""
Triton Client -- Generic Triton Inference Server client wrapper.

Base class for all service-specific Triton clients. Services inherit
and add their own I/O preparation methods.

Usage:
    from ai4icore_model_management import TritonClient

    # Direct usage
    client = TritonClient("triton-host:8000", api_key="...", timeout=30)
    result = client.send_triton_request("model_name", inputs, outputs)

    # Or inherit for service-specific I/O
    class NERTritonClient(TritonClient):
        def get_ner_io(self, texts, language):
            ...
"""

import logging
import time
from contextvars import ContextVar
from typing import Dict, List, Optional

import numpy as np
import tritonclient.http as http_client
from tritonclient.http import InferInput, InferRequestedOutput
from tritonclient.utils import np_to_triton_dtype

from ai4icore_exceptions import TritonInferenceError

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

# Optional OpenTelemetry support
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode

    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False


class TritonClient:
    """Generic Triton Inference Server client with optional tracing."""

    def __init__(
        self,
        triton_url: str,
        api_key: Optional[str] = None,
        timeout: int = 30,
    ):
        self.triton_url = self._normalize_url(triton_url)
        self.api_key = api_key
        self.timeout = timeout
        self._client: Optional[http_client.InferenceServerClient] = None

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Strip http(s):// prefix -- tritonclient expects host:port."""
        url = url.strip()
        if url.startswith("http://"):
            url = url[7:]
        elif url.startswith("https://"):
            url = url[8:]
        return url

    @property
    def client(self) -> http_client.InferenceServerClient:
        """Lazy initialization of the underlying HTTP client."""
        if self._client is None:
            logger.info("Initializing Triton client: %s", self.triton_url)
            try:
                self._client = http_client.InferenceServerClient(
                    url=self.triton_url, verbose=False
                )
            except Exception as e:
                logger.error("Failed to init Triton client '%s': %s", self.triton_url, e)
                raise TritonInferenceError(
                    f"Failed to initialize Triton client: {e}"
                ) from e
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
    ):
        """
        Send inference request to Triton. Traces automatically when OTel is available.

        Returns the raw Triton inference result.
        Raises TritonInferenceError on any failure.
        """
        start = time.perf_counter()
        try:
            if _OTEL_AVAILABLE:
                return self._send_traced(model_name, inputs, outputs, headers, model_version)
            return self._send_impl(model_name, inputs, outputs, headers, model_version)
        finally:
            _accumulate_inference_time((time.perf_counter() - start) * 1000)

    def _send_traced(
        self,
        model_name: str,
        inputs: List[InferInput],
        outputs: List[InferRequestedOutput],
        headers: Optional[Dict[str, str]],
        model_version: str,
    ):
        tracer = trace.get_tracer("ai4icore_model_management")
        with tracer.start_as_current_span("triton.inference") as span:
            span.set_attribute("triton.model_name", model_name)
            span.set_attribute("triton.endpoint", self.triton_url)
            span.set_attribute("triton.has_auth", bool(self.api_key))
            span.set_attribute("triton.input_count", len(inputs))
            span.set_attribute("triton.output_count", len(outputs))
            span.set_attribute("triton.timeout_seconds", self.timeout)
            span.add_event("triton.inference.start", {"model": model_name})

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

    def _send_impl(
        self,
        model_name: str,
        inputs: List[InferInput],
        outputs: List[InferRequestedOutput],
        headers: Optional[Dict[str, str]],
        model_version: str,
    ):
        """Core inference logic without tracing."""
        try:
            req_headers = dict(headers or {})
            if self.api_key:
                req_headers["Authorization"] = f"Bearer {self.api_key}"

            logger.debug("Triton inference: model='%s' endpoint='%s'", model_name, self.triton_url)

            async_response = self.client.async_infer(
                model_name=model_name,
                model_version=model_version,
                inputs=inputs,
                outputs=outputs,
                headers=req_headers or None,
            )
            return async_response.get_result(block=True, timeout=self.timeout)

        except Exception as e:
            error_msg = str(e)
            logger.error("Triton inference failed: model='%s' endpoint='%s' error=%s", model_name, self.triton_url, e)

            if "404" in error_msg or "Not Found" in error_msg:
                available = self.list_models()
                hint = f" Available: {', '.join(available)}" if available else ""
                raise TritonInferenceError(
                    f"Model '{model_name}' not found at '{self.triton_url}'.{hint}",
                    model_name=model_name,
                ) from e

            if "connection" in error_msg.lower():
                raise TritonInferenceError(
                    f"Cannot connect to Triton at '{self.triton_url}'. Verify endpoint and server status.",
                    model_name=model_name,
                ) from e

            raise TritonInferenceError(
                f"Triton inference failed: {e}", model_name=model_name
            ) from e

    # ------------------------------------------------------------------
    # Server introspection
    # ------------------------------------------------------------------
    def is_server_ready(self) -> bool:
        """Check if Triton server is ready to accept requests."""
        try:
            return self.client.is_server_ready()
        except Exception as e:
            logger.warning("Triton health check failed at '%s': %s", self.triton_url, e)
            return False

    def list_models(self) -> List[str]:
        """List available model names on the Triton server."""
        try:
            index = self.client.get_model_repository_index()
            return [m.get("name", "") for m in (index or [])]
        except Exception as e:
            logger.warning("Failed to list Triton models at '%s': %s", self.triton_url, e)
            return []

    # ------------------------------------------------------------------
    # Tensor helpers (common across services)
    # ------------------------------------------------------------------
    def _get_string_tensor(self, string_values: List[str], tensor_name: str) -> InferInput:
        """Create a string tensor with shape [batch, 1] for Triton input."""
        try:
            nested = [[v] for v in string_values]
            np_array = np.array(nested, dtype=object)
            tensor = InferInput(tensor_name, np_array.shape, np_to_triton_dtype(np_array.dtype))
            tensor.set_data_from_numpy(np_array)
            return tensor
        except Exception as e:
            raise TritonInferenceError(f"Failed to create tensor '{tensor_name}': {e}") from e

    def _get_bool_tensor(self, bool_values: List[bool], tensor_name: str) -> InferInput:
        """Create a boolean tensor with shape [batch, 1] for Triton input."""
        try:
            nested = [[v] for v in bool_values]
            np_array = np.array(nested, dtype=bool)
            tensor = InferInput(tensor_name, np_array.shape, np_to_triton_dtype(np_array.dtype))
            tensor.set_data_from_numpy(np_array)
            return tensor
        except Exception as e:
            raise TritonInferenceError(f"Failed to create tensor '{tensor_name}': {e}") from e
