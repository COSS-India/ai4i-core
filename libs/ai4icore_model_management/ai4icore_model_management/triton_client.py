"""
Triton Client
Generic Triton Inference Server client wrapper
"""

import logging
import numpy as np
from typing import List, Tuple, Optional, Dict, Any, Callable

import tritonclient.http as http_client
from tritonclient.utils import np_to_triton_dtype
from tritonclient.http import InferInput, InferRequestedOutput

logger = logging.getLogger(__name__)


class TritonInferenceError(Exception):
    """Triton inference error"""
    pass


class TritonClient:
    """Generic Triton Inference Server client"""
    
    def __init__(self, triton_url: str, api_key: Optional[str] = None):
        """
        Initialize Triton client
        
        Args:
            triton_url: Triton server URL (host:port format, without http://)
            api_key: Optional API key for authentication
        """
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
    
    def send_triton_request(
        self,
        model_name: str,
        inputs: List[InferInput],
        outputs: List[InferRequestedOutput],
        headers: Optional[Dict[str, str]] = None,
        model_version: str = "1"
    ):
        """
        Send inference request to Triton server
        
        Args:
            model_name: Name of the model to use
            inputs: List of InferInput objects
            outputs: List of InferRequestedOutput objects
            headers: Optional headers dict
            model_version: Model version (default: "1")
            
        Returns:
            Inference result object
        """
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
                model_version=model_version,
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
                try:
                    available_models = self.list_models()
                    if available_models:
                        raise TritonInferenceError(
                            f"Triton model '{model_name}' not found at '{self.triton_url}'. "
                            f"Available models: {', '.join(available_models)}. "
                            f"Please verify the model name is correct."
                        )
                    else:
                        raise TritonInferenceError(
                            f"Triton model '{model_name}' not found at '{self.triton_url}'. "
                            f"Could not retrieve available models. Please verify the model name and endpoint are correct."
                        )
                except Exception:
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
            # Create nested arrays to match expected shape [-1, 1]
            nested_values = [[value] for value in string_values]
            np_array = np.array(nested_values, dtype=object)
            
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

