"""
Triton Client
Triton Inference Server client wrapper for NMT
"""

import logging
import numpy as np
from typing import List, Tuple, Optional, Dict

import tritonclient.http as http_client
from tritonclient.utils import np_to_triton_dtype
from tritonclient.http import InferInput, InferRequestedOutput

logger = logging.getLogger(__name__)


class TritonInferenceError(Exception):
    """Triton inference error"""
    pass


class TritonClient:
    """Triton Inference Server client for NMT"""
    
    def __init__(self, triton_url: str, api_key: Optional[str] = None):
        self.triton_url = triton_url
        self.api_key = api_key
        self._client = None
    
    @property
    def client(self):
        """Lazy initialization of Triton client"""
        if self._client is None:
            self._client = http_client.InferenceServerClient(
                url=self.triton_url,
                verbose=False
            )
        return self._client
    
    def get_translation_io_for_triton(
        self,
        input_texts: List[str],
        source_lang: str,
        target_lang: str
    ) -> Tuple[List[InferInput], List[InferRequestedOutput]]:
        """Prepare inputs and outputs for Triton NMT inference"""
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
            
            # Create OUTPUT_TEXT output
            output_text_output = InferRequestedOutput("OUTPUT_TEXT")
            
            inputs = [input_text_input, input_lang_input, output_lang_input]
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
        try:
            # Check server health
            if not self.is_server_ready():
                raise TritonInferenceError("Triton server is not ready")
            
            # Prepare headers
            if headers is None:
                headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
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
            logger.error(f"Triton inference request failed: {e}")
            raise TritonInferenceError(f"Triton inference request failed: {e}")
    
    def is_server_ready(self) -> bool:
        """Check if Triton server is ready"""
        try:
            return self.client.is_server_ready()
        except Exception as e:
            logger.error(f"Failed to check Triton server status: {e}")
            return False
    
    def _get_string_tensor(self, string_values: List[str], tensor_name: str) -> InferInput:
        """Create string tensor for Triton input"""
        try:
            # Create numpy array with dtype="object"
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
