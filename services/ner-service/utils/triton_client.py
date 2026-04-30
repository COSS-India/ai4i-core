"""
Triton Client
Triton Inference Server client wrapper for NER
"""

import logging
from typing import List, Tuple, Optional, Dict

import numpy as np
import tritonclient.http as http_client
from tritonclient.utils import np_to_triton_dtype
from tritonclient.http import InferInput, InferRequestedOutput
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger(__name__)
# Use service name to get the same tracer instance as main.py
tracer = trace.get_tracer("ner-service")


class TritonInferenceError(Exception):
    """Triton inference error"""

    pass


class TritonClient:
    """Triton Inference Server client for NER"""

    def __init__(self, triton_url: str, api_key: Optional[str] = None):
        # Normalize URL - ensure it has host:port format (no http:// prefix)
        self.triton_url = self._normalize_url(triton_url)
        self.api_key = api_key
        self._client: Optional[http_client.InferenceServerClient] = None

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize Triton URL to ensure proper format."""
        url = url.strip()
        if url.startswith("http://"):
            url = url[7:]
        elif url.startswith("https://"):
            url = url[8:]
        return url

    @property
    def client(self) -> http_client.InferenceServerClient:
        """Lazy initialization of Triton client"""
        if self._client is None:
            logger.info("Initializing Triton client with URL: %s", self.triton_url)
            try:
                self._client = http_client.InferenceServerClient(
                    url=self.triton_url,
                    verbose=False,
                )
            except Exception as e:
                logger.error(
                    "Failed to initialize Triton client with URL '%s': %s",
                    self.triton_url,
                    e,
                    exc_info=True,
                )
                raise TritonInferenceError(
                    f"Failed to initialize Triton client: {e}"
                ) from e
        return self._client

    def _get_string_tensor(self, string_values: List[str], tensor_name: str) -> InferInput:
        """Create string tensor for Triton input (shape [batch, 1])"""
        try:
            nested_values = [[value] for value in string_values]
            np_array = np.array(nested_values, dtype=object)

            input_tensor = InferInput(
                tensor_name,
                np_array.shape,
                np_to_triton_dtype(np_array.dtype),
            )

            input_tensor.set_data_from_numpy(np_array)
            return input_tensor
        except Exception as e:
            logger.error("Failed to create string tensor %s: %s", tensor_name, e)
            raise TritonInferenceError(f"Failed to create string tensor: {e}") from e

    def get_ner_io_for_triton(
        self,
        input_texts: List[str],
        language: str,
    ) -> Tuple[List[InferInput], List[InferRequestedOutput]]:
        """
        Prepare inputs and outputs for Triton NER inference.

        - INPUT_TEXT: [[text1], [text2], ...]
        - LANG_ID:    [[lang], [lang], ...]
        - OUTPUT_TEXT: JSON-encoded predictions.
        """
        try:
            input_text_input = self._get_string_tensor(input_texts, "INPUT_TEXT")
            lang_input = self._get_string_tensor(
                [language] * len(input_texts),
                "LANG_ID",
            )

            output_text_output = InferRequestedOutput("OUTPUT_TEXT")

            inputs = [input_text_input, lang_input]
            outputs = [output_text_output]
            return inputs, outputs
        except Exception as e:
            logger.error("Failed to prepare Triton I/O for NER: %s", e)
            raise TritonInferenceError(f"Failed to prepare Triton I/O: {e}") from e

    def send_triton_request(
        self,
        model_name: str,
        inputs: List[InferInput],
        outputs: List[InferRequestedOutput],
        headers: Optional[Dict[str, str]] = None,
    ):
        """Send inference request to Triton server (synchronous)."""
        if not tracer:
            # Fallback if tracing not available
            return self._send_triton_request_impl(model_name, inputs, outputs, headers)
        
        with tracer.start_as_current_span("triton.inference") as span:
            try:
                span.set_attribute("triton.model_name", model_name)
                span.set_attribute("triton.endpoint", self.triton_url)
                span.set_attribute("triton.has_auth", bool(self.api_key))
                
                # Calculate input size (approximate)
                try:
                    total_size = sum(
                        len(inp.get_data()) if hasattr(inp, 'get_data') else 0
                        for inp in inputs
                    )
                    span.set_attribute("triton.input_size_bytes", total_size)
                except Exception:
                    pass
                
                span.set_attribute("triton.input_count", len(inputs))
                span.set_attribute("triton.output_count", len(outputs))
                
                # Add span event for Triton call start
                span.add_event("triton.inference.start", {
                    "model": model_name,
                    "endpoint": self.triton_url
                })
                
                if headers is None:
                    headers = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"

                logger.debug(
                    "Sending NER inference request to model '%s' at '%s'",
                    model_name,
                    self.triton_url,
                )

                # Use async_infer with timeout (like NMT service) to avoid hanging
                import os
                timeout = int(os.getenv("TRITON_TIMEOUT", "30"))
                span.set_attribute("triton.timeout_seconds", timeout)
                
                # Send async inference request
                async_response = self.client.async_infer(
                    model_name=model_name,
                    model_version="1",
                    inputs=inputs,
                    outputs=outputs,
                    headers=headers or None,
                )
                
                # Get result with timeout
                response = async_response.get_result(block=True, timeout=timeout)
                
                span.set_attribute("triton.status", "success")
                span.add_event("triton.inference.complete", {"status": "success"})
                
                # Try to get output size (approximate)
                try:
                    for output_name in [out.name() for out in outputs]:
                        output_data = response.as_numpy(output_name)
                        if output_data is not None:
                            output_size = output_data.nbytes if hasattr(output_data, 'nbytes') else 0
                            span.set_attribute(f"triton.output.{output_name}.size_bytes", output_size)
                except Exception:
                    pass
                
                return response
                
            except Exception as e:
                error_msg = str(e)
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", error_msg)
                span.set_attribute("triton.status", "failed")
                span.set_status(Status(StatusCode.ERROR, error_msg))
                span.record_exception(e)
                span.add_event("triton.inference.failed", {
                    "error_type": type(e).__name__,
                    "error_message": error_msg
                })
                
                logger.error(
                    "Triton inference request failed for model '%s' at '%s': %s",
                    model_name,
                    self.triton_url,
                    e,
                    exc_info=True,
                )
                if "Connection" in error_msg or "connect" in error_msg.lower():
                    raise TritonInferenceError(
                        f"Cannot connect to Triton server at '{self.triton_url}'. "
                        f"Please verify the endpoint is correct and the server is running."
                    ) from e
                raise TritonInferenceError(f"Triton inference request failed: {e}") from e
    
    def _send_triton_request_impl(
        self,
        model_name: str,
        inputs: List[InferInput],
        outputs: List[InferRequestedOutput],
        headers: Optional[Dict[str, str]] = None,
    ):
        """Fallback implementation when tracing is not available."""
        try:
            if headers is None:
                headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            logger.debug(
                "Sending NER inference request to model '%s' at '%s'",
                model_name,
                self.triton_url,
            )

            # Use async_infer with timeout to avoid hanging
            import os
            timeout = int(os.getenv("TRITON_TIMEOUT", "30"))
            
            # Send async inference request
            async_response = self.client.async_infer(
                model_name=model_name,
                model_version="1",
                inputs=inputs,
                outputs=outputs,
                headers=headers or None,
            )
            
            # Get result with timeout
            response = async_response.get_result(block=True, timeout=timeout)
            return response
        except Exception as e:
            error_msg = str(e)
            logger.error(
                "Triton inference request failed for model '%s' at '%s': %s",
                model_name,
                self.triton_url,
                e,
                exc_info=True,
            )
            if "Connection" in error_msg or "connect" in error_msg.lower():
                raise TritonInferenceError(
                    f"Cannot connect to Triton server at '{self.triton_url}'. "
                    f"Please verify the endpoint is correct and the server is running."
                ) from e
            raise TritonInferenceError(f"Triton inference request failed: {e}") from e



