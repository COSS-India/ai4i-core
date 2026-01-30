"""
Triton Client
Triton Inference Server client wrapper for transliteration
"""

import logging
import numpy as np
from typing import List, Tuple, Optional, Dict

import tritonclient.http as http_client
from tritonclient.utils import np_to_triton_dtype
from tritonclient.http import InferInput, InferRequestedOutput

# OpenTelemetry imports
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    tracer = trace.get_tracer("transliteration-service")
    TRACING_AVAILABLE = True
except ImportError:
    tracer = None
    TRACING_AVAILABLE = False

logger = logging.getLogger(__name__)


class TritonInferenceError(Exception):
    """Triton inference error"""
    pass


class TritonClient:
    """Triton Inference Server client for transliteration"""
    
    def __init__(self, triton_url: str, api_key: Optional[str] = None):
        # Normalize URL - ensure it doesn't have http:// prefix
        self.triton_url = self._normalize_url(triton_url)
        self.api_key = api_key
        self._client = None
    
    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize Triton URL to ensure proper format
        
        Triton HTTP client expects host:port format, NOT http://host:port
        """
        url = url.strip()
        # Remove http:// or https:// prefix if present
        if url.startswith("http://"):
            url = url[7:]
        elif url.startswith("https://"):
            url = url[8:]
        return url
    
    @property
    def client(self):
        """Lazy initialization of Triton client"""
        if self._client is None:
            logger.info(f"Initializing Triton client with URL: {self.triton_url}")
            try:
                self._client = http_client.InferenceServerClient(
                    url=self.triton_url,
                    verbose=False
                )
            except Exception as e:
                logger.error(f"Failed to initialize Triton client with URL '{self.triton_url}': {e}", exc_info=True)
                raise
        return self._client
    
    def get_transliteration_io_for_triton(
        self,
        input_texts: List[str],
        source_lang: str,
        target_lang: str,
        is_word_level: bool,
        top_k: int = 0
    ) -> Tuple[List[InferInput], List[InferRequestedOutput]]:
        """Prepare inputs and outputs for Triton transliteration inference"""
        try:
            # Create INPUT_TEXT input (BYTES)
            input_text_input = self._get_string_tensor(input_texts, "INPUT_TEXT")
            
            # Create INPUT_LANGUAGE_ID input (BYTES)
            input_lang_input = self._get_string_tensor(
                [source_lang] * len(input_texts), 
                "INPUT_LANGUAGE_ID"
            )
            
            # Create OUTPUT_LANGUAGE_ID input (BYTES)
            output_lang_input = self._get_string_tensor(
                [target_lang] * len(input_texts), 
                "OUTPUT_LANGUAGE_ID"
            )
            
            # Create IS_WORD_LEVEL input (BOOL)
            is_word_level_input = self._get_bool_tensor(
                [is_word_level] * len(input_texts),
                "IS_WORD_LEVEL"
            )
            
            # Create TOP_K input (UINT8)
            top_k_input = self._get_uint8_tensor(
                [top_k] * len(input_texts),
                "TOP_K"
            )
            
            # Create OUTPUT_TEXT output
            output_text_output = InferRequestedOutput("OUTPUT_TEXT")
            
            inputs = [
                input_text_input,
                input_lang_input,
                output_lang_input,
                is_word_level_input,
                top_k_input
            ]
            outputs = [output_text_output]
            
            return inputs, outputs
            
        except Exception as e:
            logger.error(f"Failed to prepare Triton I/O: {e}")
            raise TritonInferenceError(f"Failed to prepare Triton I/O: {e}")
    
    def send_triton_request(
        self,
        model_name: str,
        inputs: List[InferInput],
        outputs: List[InferRequestedOutput],
        headers: Optional[Dict[str, str]] = None
    ):
        """Send inference request to Triton server"""
        if not tracer:
            # Fallback if tracing not available
            return self._send_triton_request_impl(model_name, inputs, outputs, headers)
        
        with tracer.start_as_current_span("triton.inference") as span:
            try:
                span.set_attribute("triton.model_name", model_name)
                span.set_attribute("triton.endpoint", self.triton_url)
                span.set_attribute("triton.has_auth", bool(self.api_key))
                span.set_attribute("triton.input_count", len(inputs))
                span.set_attribute("triton.output_count", len(outputs))
                
                # Calculate input size (approximate)
                try:
                    total_size = sum(
                        len(inp.get_data()) if hasattr(inp, 'get_data') else 0
                        for inp in inputs
                    )
                    span.set_attribute("triton.input_size_bytes", total_size)
                except Exception:
                    pass
                
                # Add span event for Triton call start
                span.add_event("triton.inference.start", {
                    "model": model_name,
                    "endpoint": self.triton_url
                })
                
                result = self._send_triton_request_impl(model_name, inputs, outputs, headers)
                
                # Add span event for Triton call completion
                span.add_event("triton.inference.complete", {
                    "model": model_name
                })
                span.set_status(Status(StatusCode.OK))
                
                logger.debug(f"Triton inference completed for model {model_name}")
                return result
                
            except Exception as e:
                error_msg = str(e)
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", error_msg)
                span.set_status(Status(StatusCode.ERROR, error_msg))
                span.record_exception(e)
                raise
    
    def _send_triton_request_impl(
        self,
        model_name: str,
        inputs: List[InferInput],
        outputs: List[InferRequestedOutput],
        headers: Optional[Dict[str, str]] = None
    ):
        """Implementation of send_triton_request without tracing"""
        try:
            # Check server health (non-blocking - log warning but try anyway)
            if not self.is_server_ready():
                logger.warning(
                    f"Triton server health check failed for '{self.triton_url}', "
                    f"but attempting inference request anyway for model '{model_name}'"
                )
            
            # Prepare headers
            if headers is None:
                headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            logger.debug(f"Sending inference request to model '{model_name}' at '{self.triton_url}'")
            
            # Send async inference request
            response = self.client.async_infer(
                model_name=model_name,
                model_version="1",
                inputs=inputs,
                outputs=outputs,
                headers=headers
            )
            
            # Get result with timeout
            result = response.get_result(block=True, timeout=20)
            return result
            
        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"Triton inference request failed for model '{model_name}' at '{self.triton_url}': {e}",
                exc_info=True
            )
            # Provide more helpful error messages
            if "404" in error_msg or "Not Found" in error_msg:
                raise TritonInferenceError(
                    f"Triton model '{model_name}' not found at '{self.triton_url}'. "
                    f"Please verify the model name and endpoint are correct."
                )
            elif "Connection" in error_msg or "connect" in error_msg.lower():
                raise TritonInferenceError(
                    f"Cannot connect to Triton server at '{self.triton_url}'. "
                    f"Please verify the endpoint is correct and the server is running."
                )
            raise TritonInferenceError(f"Triton inference request failed: {e}")
    
    def is_server_ready(self) -> bool:
        """Check if Triton server is ready"""
        try:
            ready = self.client.is_server_ready()
            if not ready:
                logger.warning(f"Triton server at '{self.triton_url}' is not ready")
            return ready
        except Exception as e:
            logger.error(f"Failed to check Triton server status at '{self.triton_url}': {e}", exc_info=True)
            return False
    
    def list_models(self) -> List[str]:
        """List all available models on the Triton server"""
        try:
            models = self.client.get_model_repository_index()
            model_names = []
            if models:
                for model in models:
                    model_names.append(model.get('name', ''))
            logger.info(f"Found {len(model_names)} models at '{self.triton_url}': {model_names}")
            return model_names
        except Exception as e:
            logger.error(f"Failed to list models from Triton server at '{self.triton_url}': {e}", exc_info=True)
            return []
    
    def _get_string_tensor(self, string_values: List[str], tensor_name: str) -> InferInput:
        """Create string tensor for Triton input"""
        try:
            # Create 1D array for batch processing - shape: [batch_size]
            np_array = np.array(string_values, dtype=object)
            
            # Create InferInput
            input_tensor = InferInput(
                tensor_name,
                np_array.shape,
                np_to_triton_dtype(np_array.dtype)
            )
            
            # Set data
            input_tensor.set_data_from_numpy(np_array)
            
            return input_tensor
            
        except Exception as e:
            logger.error(f"Failed to create string tensor {tensor_name}: {e}")
            raise TritonInferenceError(f"Failed to create string tensor: {e}")
    
    def _get_bool_tensor(self, bool_values: List[bool], tensor_name: str) -> InferInput:
        """Create bool tensor for Triton input"""
        try:
            np_array = np.array(bool_values, dtype=bool)
            
            # Create InferInput
            input_tensor = InferInput(
                tensor_name,
                np_array.shape,
                np_to_triton_dtype(np_array.dtype)
            )
            
            # Set data
            input_tensor.set_data_from_numpy(np_array)
            
            return input_tensor
            
        except Exception as e:
            logger.error(f"Failed to create bool tensor {tensor_name}: {e}")
            raise TritonInferenceError(f"Failed to create bool tensor: {e}")
    
    def _get_uint8_tensor(self, uint8_values: List[int], tensor_name: str) -> InferInput:
        """Create uint8 tensor for Triton input"""
        try:
            np_array = np.array(uint8_values, dtype=np.uint8)
            
            # Create InferInput
            input_tensor = InferInput(
                tensor_name,
                np_array.shape,
                np_to_triton_dtype(np_array.dtype)
            )
            
            # Set data
            input_tensor.set_data_from_numpy(np_array)
            
            return input_tensor
            
        except Exception as e:
            logger.error(f"Failed to create uint8 tensor {tensor_name}: {e}")
            raise TritonInferenceError(f"Failed to create uint8 tensor: {e}")

