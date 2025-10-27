"""
HTTP Client utilities for calling other microservices.

Provides an async HTTP client for making requests to ASR, NMT, and TTS services.
"""

import os
import logging
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)


class ServiceClient:
    """HTTP client for calling AI microservices."""
    
    def __init__(self):
        """Initialize the service client with base URLs."""
        # Get service URLs from environment variables
        self.asr_service_url = os.getenv('ASR_SERVICE_URL', 'http://asr-service:8087')
        self.nmt_service_url = os.getenv('NMT_SERVICE_URL', 'http://nmt-service:8089')
        self.tts_service_url = os.getenv('TTS_SERVICE_URL', 'http://tts-service:8088')
        
        # Remove trailing slashes
        self.asr_service_url = self.asr_service_url.rstrip('/')
        self.nmt_service_url = self.nmt_service_url.rstrip('/')
        self.tts_service_url = self.tts_service_url.rstrip('/')
        
        # Create HTTP client
        self.client = httpx.AsyncClient(timeout=300.0)  # 5 minute timeout for inference
    
    async def call_asr_service(self, request_data: Dict[str, Any], api_key: Optional[str] = None) -> Dict[str, Any]:
        """Call ASR service for speech-to-text conversion."""
        headers = {}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        
        logger.info(f"Calling ASR service: {self.asr_service_url}/api/v1/asr/inference")
        
        try:
            response = await self.client.post(
                f"{self.asr_service_url}/api/v1/asr/inference",
                json=request_data,
                headers=headers
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"ASR service error: {e}")
            raise ValueError(f"ASR service error: {str(e)}") from e
    
    async def call_nmt_service(self, request_data: Dict[str, Any], api_key: Optional[str] = None) -> Dict[str, Any]:
        """Call NMT service for translation."""
        headers = {}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        
        logger.info(f"Calling NMT service: {self.nmt_service_url}/api/v1/nmt/inference")
        
        try:
            response = await self.client.post(
                f"{self.nmt_service_url}/api/v1/nmt/inference",
                json=request_data,
                headers=headers
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"NMT service error: {e}")
            raise ValueError(f"NMT service error: {str(e)}") from e
    
    async def call_tts_service(self, request_data: Dict[str, Any], api_key: Optional[str] = None) -> Dict[str, Any]:
        """Call TTS service for text-to-speech conversion."""
        headers = {}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        
        logger.info(f"Calling TTS service: {self.tts_service_url}/api/v1/tts/inference")
        
        try:
            response = await self.client.post(
                f"{self.tts_service_url}/api/v1/tts/inference",
                json=request_data,
                headers=headers
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"TTS service error: {e}")
            raise ValueError(f"TTS service error: {str(e)}") from e
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
