"""
Triton Inference Server client wrapper.

Adapted from Dhruva-Platform-2 triton_utils_service.py and inference_gateway.py.
"""

import logging
import os
from typing import List, Tuple, Optional, Dict
import numpy as np
import tritonclient.http as http_client
from tritonclient.utils import np_to_triton_dtype
import gevent.ssl

from middleware.exceptions import (
    TritonInferenceError,
    ModelNotFoundError,
    ServiceUnavailableError
)

logger = logging.getLogger(__name__)


class TritonClient:
    """Triton Inference Server client for ASR operations."""
    
    def __init__(self, triton_url: str, api_key: Optional[str] = None):
        """Initialize Triton client."""
        self.triton_url = triton_url
        self.api_key = api_key
        self._client = None
    
    def _get_client(self):
        """Get or create Triton client (lazy initialization)."""
        if self._client is None:
            try:
                # Create client (simplified SSL configuration)
                self._client = http_client.InferenceServerClient(
                    url=self.triton_url,
                    ssl=False  # Disable SSL for local development
                )
                
                logger.info(f"Initialized Triton client for {self.triton_url}")
                
            except Exception as e:
                logger.error(f"Failed to initialize Triton client: {e}")
                raise TritonInferenceError(f"Failed to initialize Triton client: {e}")
        
        return self._client
    
    def get_asr_io_for_triton(
        self,
        audio_chunks: List[np.ndarray],
        service_id: str,
        language: str,
        n_best_tok: int = 0
    ) -> Tuple[List[http_client.InferInput], List[http_client.InferRequestedOutput]]:
        """Prepare inputs and outputs for ASR Triton inference."""
        try:
            # Pad batch to the actual max length in this batch (not fixed 16000)
            padded_audio, num_samples = self._pad_batch(audio_chunks)
            
            # Log the actual shape we're sending
            logger.debug(f"Sending audio to Triton with shape: {padded_audio.shape}")
            
            # Create inputs
            inputs = []
            
            # AUDIO_SIGNAL input (FP32) - use actual padded shape as list
            batch_size, max_length = padded_audio.shape
            audio_input = http_client.InferInput(
                "AUDIO_SIGNAL",
                [batch_size, max_length],  # Use actual shape as list
                np_to_triton_dtype(np.float32)
            )
            audio_input.set_data_from_numpy(padded_audio.astype(np.float32))
            inputs.append(audio_input)
            
            # NUM_SAMPLES input (INT32) - shape [batch_size, 1]
            num_samples_input = http_client.InferInput(
                "NUM_SAMPLES",
                [batch_size, 1],  # Shape as list
                np_to_triton_dtype(np.int32)
            )
            # Reshape to [batch_size, 1]
            num_samples_reshaped = num_samples.reshape(-1, 1)
            num_samples_input.set_data_from_numpy(num_samples_reshaped.astype(np.int32))
            inputs.append(num_samples_input)
            
            # LANG_ID input (BYTES) - shape [batch_size, 1]
            lang_ids = [language.encode('utf-8') for _ in range(len(audio_chunks))]
            lang_input = self._get_string_tensor(lang_ids, "LANG_ID")
            inputs.append(lang_input)
            
            # TOPK input (INT32) - shape [batch_size, 1] - only if n_best_tok > 0
            if n_best_tok > 0:
                topk_values = np.array([[n_best_tok]] * len(audio_chunks), dtype=np.int32)  # [batch_size, 1]
                topk_input = http_client.InferInput(
                    "TOPK",
                    [batch_size, 1],  # Shape as list
                    np_to_triton_dtype(np.int32)
                )
                topk_input.set_data_from_numpy(topk_values)
                inputs.append(topk_input)
            
            # Create outputs
            outputs = []
            transcripts_output = http_client.InferRequestedOutput("TRANSCRIPTS")
            outputs.append(transcripts_output)
            
            return inputs, outputs
            
        except Exception as e:
            logger.error(f"Failed to prepare ASR IO for Triton: {e}")
            raise TritonInferenceError(f"Failed to prepare ASR IO: {e}")
    
    def get_vad_io_for_triton(
        self,
        audio: np.ndarray,
        sample_rate: int,
        threshold: float,
        min_silence_duration_ms: int,
        speech_pad_ms: int,
        min_speech_duration_ms: int
    ) -> Tuple[List[http_client.InferInput], List[http_client.InferRequestedOutput]]:
        """Prepare inputs and outputs for VAD Triton inference."""
        try:
            # Pad audio
            padded_audio, num_samples = self._pad_batch([audio])
            
            # Create inputs
            inputs = []
            
            # WAVPATH input (FP32)
            wavpath_input = http_client.InferInput(
                "WAVPATH",
                padded_audio.shape,
                np_to_triton_dtype(padded_audio.dtype)
            )
            wavpath_input.set_data_from_numpy(padded_audio)
            inputs.append(wavpath_input)
            
            # SAMPLING_RATE input (INT32)
            sampling_rate_values = np.array([sample_rate], dtype=np.int32)
            sampling_rate_input = http_client.InferInput(
                "SAMPLING_RATE",
                sampling_rate_values.shape,
                np_to_triton_dtype(sampling_rate_values.dtype)
            )
            sampling_rate_input.set_data_from_numpy(sampling_rate_values)
            inputs.append(sampling_rate_input)
            
            # THRESHOLD input (FP32)
            threshold_values = np.array([threshold], dtype=np.float32)
            threshold_input = http_client.InferInput(
                "THRESHOLD",
                threshold_values.shape,
                np_to_triton_dtype(threshold_values.dtype)
            )
            threshold_input.set_data_from_numpy(threshold_values)
            inputs.append(threshold_input)
            
            # MIN_SILENCE_DURATION_MS input (INT32)
            min_silence_values = np.array([min_silence_duration_ms], dtype=np.int32)
            min_silence_input = http_client.InferInput(
                "MIN_SILENCE_DURATION_MS",
                min_silence_values.shape,
                np_to_triton_dtype(min_silence_values.dtype)
            )
            min_silence_input.set_data_from_numpy(min_silence_values)
            inputs.append(min_silence_input)
            
            # SPEECH_PAD_MS input (INT32)
            speech_pad_values = np.array([speech_pad_ms], dtype=np.int32)
            speech_pad_input = http_client.InferInput(
                "SPEECH_PAD_MS",
                speech_pad_values.shape,
                np_to_triton_dtype(speech_pad_values.dtype)
            )
            speech_pad_input.set_data_from_numpy(speech_pad_values)
            inputs.append(speech_pad_input)
            
            # MIN_SPEECH_DURATION_MS input (INT32)
            min_speech_values = np.array([min_speech_duration_ms], dtype=np.int32)
            min_speech_input = http_client.InferInput(
                "MIN_SPEECH_DURATION_MS",
                min_speech_values.shape,
                np_to_triton_dtype(min_speech_values.dtype)
            )
            min_speech_input.set_data_from_numpy(min_speech_values)
            inputs.append(min_speech_input)
            
            # Create outputs
            outputs = []
            timestamps_output = http_client.InferRequestedOutput("TIMESTAMPS")
            outputs.append(timestamps_output)
            
            return inputs, outputs
            
        except Exception as e:
            logger.error(f"Failed to prepare VAD IO for Triton: {e}")
            raise TritonInferenceError(f"Failed to prepare VAD IO: {e}")
    
    def list_models(self) -> List[str]:
        """List all available models on the Triton server"""
        try:
            client = self._get_client()
            models = client.get_model_repository_index()
            model_names = []
            if models:
                for model in models:
                    model_names.append(model.get('name', ''))
            logger.info(f"Found {len(model_names)} models at '{self.triton_url}': {model_names}")
            return model_names
        except Exception as e:
            logger.error(f"Failed to list models from Triton server at '{self.triton_url}': {e}", exc_info=True)
            return []
    
    def send_triton_request(
        self,
        model_name: str,
        input_list: List[http_client.InferInput],
        output_list: List[http_client.InferRequestedOutput],
        headers: Optional[Dict[str, str]] = None
    ) -> http_client.InferResult:
        """Send inference request to Triton server."""
        try:
            client = self._get_client()
            
            # Check server health
            if not client.is_server_ready():
                raise TritonInferenceError("Triton server is not ready")
            
            # Prepare headers
            request_headers = {}
            if self.api_key:
                request_headers["Authorization"] = f"Bearer {self.api_key}"
            if headers:
                request_headers.update(headers)
            
            # Send async inference request
            response = client.async_infer(
                model_name=model_name,
                inputs=input_list,
                model_version="1",
                outputs=output_list,
                headers=request_headers
            )
            
            # Get result with timeout
            timeout = int(os.getenv("TRITON_TIMEOUT", "20"))
            result = response.get_result(block=True, timeout=timeout)
            
            logger.debug(f"Triton inference completed for model {model_name}")
            return result
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Triton inference failed for model {model_name}: {e}", exc_info=True)
            
            # Provide more helpful error messages with proper error codes
            if "404" in error_msg or "Not Found" in error_msg or "unknown model" in error_msg.lower():
                raise ModelNotFoundError(
                    message=f"Triton model '{model_name}' not found. Please verify the model name and ensure it is loaded.",
                    model_name=model_name
                )
            elif "Connection" in error_msg or "connect" in error_msg.lower() or "timeout" in error_msg.lower():
                raise ServiceUnavailableError(
                    message=f"Cannot connect to Triton server. Please verify the endpoint is correct and the server is running.",
                    service_name="triton"
                )
            raise TritonInferenceError(
                message=f"Triton inference failed: {error_msg}",
                model_name=model_name
            )
    
    def _pad_batch(self, batch_data: List[np.ndarray]) -> Tuple[np.ndarray, np.ndarray]:
        """Pad batch data to same length."""
        if not batch_data:
            return np.array([]), np.array([])
        
        # Calculate max length in batch
        max_length = max(len(item) for item in batch_data)
        batch_size = len(batch_data)
        
        # Create zero-padded array
        padded_array = np.zeros((batch_size, max_length), dtype=batch_data[0].dtype)
        lengths_array = np.zeros(batch_size, dtype=np.int32)
        
        # Fill with actual data
        for i, item in enumerate(batch_data):
            length = len(item)
            padded_array[i, :length] = item
            lengths_array[i] = length
        
        return padded_array, lengths_array
    
    def _get_string_tensor(self, string_values: List, tensor_name: str) -> http_client.InferInput:
        """Create string tensor input with proper batch dimensions."""
        # Create numpy array with dtype="object" and reshape to [batch_size, 1]
        string_array = np.array(string_values, dtype=object).reshape(-1, 1)
        batch_size = string_array.shape[0]
        
        # Create InferInput with shape [batch_size, 1]
        string_input = http_client.InferInput(
            tensor_name,
            [batch_size, 1],  # Shape as list
            np_to_triton_dtype(string_array.dtype)
        )
        string_input.set_data_from_numpy(string_array)
        
        return string_input
    
    def _get_bool_tensor(self, bool_values: List, tensor_name: str) -> http_client.InferInput:
        """Create boolean tensor input."""
        bool_array = np.array(bool_values, dtype=bool)
        
        bool_input = http_client.InferInput(
            tensor_name,
            bool_array.shape,
            np_to_triton_dtype(bool_array.dtype)
        )
        bool_input.set_data_from_numpy(bool_array)
        
        return bool_input
    
    def _get_uint8_tensor(self, uint8_values: List, tensor_name: str) -> http_client.InferInput:
        """Create uint8 tensor input."""
        uint8_array = np.array(uint8_values, dtype=np.uint8)
        
        uint8_input = http_client.InferInput(
            tensor_name,
            uint8_array.shape,
            np_to_triton_dtype(uint8_array.dtype)
        )
        uint8_input.set_data_from_numpy(uint8_array)
        
        return uint8_input
