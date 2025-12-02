"""
Triton Client for LLM Service
Client for calling LLM inference endpoint
"""

import logging
import httpx
from typing import List, Optional, Dict, Any
import json

logger = logging.getLogger(__name__)


class TritonInferenceError(Exception):
    """Triton inference error"""
    pass


class TritonClient:
    """Client for LLM inference endpoint"""
    
    def __init__(self, triton_url: str, api_key: Optional[str] = None, timeout: float = 300.0):
        # Extract base URL from triton_url (remove http:// or https:// if needed)
        if not triton_url.startswith(('http://', 'https://')):
            self.triton_url = f"http://{triton_url}"
        else:
            self.triton_url = triton_url
        self.api_key = api_key
        self.timeout = timeout
        self._client = None
    
    @property
    def client(self):
        """Lazy initialization of HTTP client"""
        if self._client is None:
            logger.info(f"Initializing HTTP client with URL: {self.triton_url}, timeout: {self.timeout}s")
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client
    
    def get_llm_io_for_triton(
        self,
        input_texts: List[str],
        input_language: Optional[str],
        output_language: Optional[str]
    ) -> Dict[str, Any]:
        """Prepare request payload for LLM inference"""
        try:
            # Default language values
            input_lang = input_language or "en"
            output_lang = output_language or "en"
            
            # Build the request payload matching the curl example
            payload = {
                "inputs": [
                    {
                        "name": "INPUT_TEXT",
                        "datatype": "BYTES",
                        "shape": [len(input_texts), 1],
                        "data": input_texts
                    },
                    {
                        "name": "INPUT_LANGUAGE_ID",
                        "datatype": "BYTES",
                        "shape": [len(input_texts), 1],
                        "data": [input_lang] * len(input_texts)
                    },
                    {
                        "name": "OUTPUT_LANGUAGE_ID",
                        "datatype": "BYTES",
                        "shape": [len(input_texts), 1],
                        "data": [output_lang] * len(input_texts)
                    }
                ],
                "outputs": [
                    {
                        "name": "OUTPUT_TEXT"
                    }
                ]
            }
            
            return payload
            
        except Exception as e:
            logger.error(f"Failed to prepare LLM I/O: {e}")
            raise TritonInferenceError(f"Failed to prepare LLM I/O: {e}")
    
    async def send_triton_request(
        self,
        model_name: str,
        inputs: List[str],
        input_language: Optional[str],
        output_language: Optional[str],
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Send inference request to LLM endpoint"""
        try:
            # Prepare headers
            if headers is None:
                headers = {}
            headers["Content-Type"] = "application/json"
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            # Prepare payload
            payload = self.get_llm_io_for_triton(inputs, input_language, output_language)
            
            # Build endpoint URL
            # endpoint_url = f"{self.triton_url}/services/inference/{model_name}"
            endpoint_url = f"{self.triton_url}/v2/models/llm/infer"            
            logger.info(f"Sending LLM inference request to {endpoint_url}")
            
            # Send HTTP request
            response = await self.client.post(
                endpoint_url,
                json=payload,
                headers=headers
            )
            
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"LLM inference request completed successfully")
            return result
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error during LLM inference: {e}")
            raise TritonInferenceError(f"HTTP error during LLM inference: {e}")
        except Exception as e:
            logger.error(f"LLM inference request failed: {e}")
            raise TritonInferenceError(f"LLM inference request failed: {e}")
    
    def is_server_ready(self) -> bool:
        """Check if LLM server is ready"""
        try:
            # Try a simple health check if available
            # For now, assume server is ready if URL is configured
            return bool(self.triton_url)
        except Exception as e:
            logger.error(f"Failed to check LLM server status: {e}")
            return False
    
    async def close(self):
        """Close HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None
