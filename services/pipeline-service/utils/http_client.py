"""
HTTP Client utilities for calling other microservices.

Provides an async HTTP client for making requests to ASR, NMT, and TTS services.
"""

import os
import logging
from typing import Dict, Any, Optional
import httpx
from .service_registry_client import ServiceRegistryHttpClient

logger = logging.getLogger(__name__)


class ServiceClient:
    """HTTP client for calling AI microservices via service discovery."""
    
    def __init__(self):
        """Initialize the service client with service registry."""
        # Registry client for discovery (HTTP-backed, e.g. config-service → ZooKeeper)
        self._registry_client = ServiceRegistryHttpClient()
        
        # Service URLs will be discovered via registry (no hardcoded defaults)
        self.asr_service_url: Optional[str] = None
        self.nmt_service_url: Optional[str] = None
        self.tts_service_url: Optional[str] = None
        
        self._discovered: bool = False

        # Create HTTP client
        self.client = httpx.AsyncClient(timeout=300.0)  # 5 minute timeout for inference

    async def _ensure_urls(self) -> None:
        """Discover service URLs via service registry. Raises if services are not found."""
        if self._discovered:
            return

        try:
            # Discover all services via registry
            # Environment variables can override discovery if explicitly set
            asr_env = os.getenv('ASR_SERVICE_URL')
            nmt_env = os.getenv('NMT_SERVICE_URL')
            tts_env = os.getenv('TTS_SERVICE_URL')
            
            if asr_env:
                self.asr_service_url = asr_env.rstrip('/')
                logger.info("ASR service URL provided via environment: %s", self.asr_service_url)
            else:
                url = await self._registry_client.discover_url('asr-service')
                if not url:
                    raise ValueError("ASR service not found in service registry. Ensure asr-service is registered.")
                self.asr_service_url = url.rstrip('/')
                logger.info("ASR service URL discovered via registry: %s", self.asr_service_url)
            
            if nmt_env:
                self.nmt_service_url = nmt_env.rstrip('/')
                logger.info("NMT service URL provided via environment: %s", self.nmt_service_url)
            else:
                url = await self._registry_client.discover_url('nmt-service')
                if not url:
                    raise ValueError("NMT service not found in service registry. Ensure nmt-service is registered.")
                self.nmt_service_url = url.rstrip('/')
                logger.info("NMT service URL discovered via registry: %s", self.nmt_service_url)
            
            if tts_env:
                self.tts_service_url = tts_env.rstrip('/')
                logger.info("TTS service URL provided via environment: %s", self.tts_service_url)
            else:
                url = await self._registry_client.discover_url('tts-service')
                if not url:
                    raise ValueError("TTS service not found in service registry. Ensure tts-service is registered.")
                self.tts_service_url = url.rstrip('/')
                logger.info("TTS service URL discovered via registry: %s", self.tts_service_url)
        except Exception as e:
            logger.error(f"Service discovery failed: {e}")
            raise ValueError(f"Failed to discover required services: {e}") from e
        finally:
            # Mark as attempted to avoid re-discovery per request; TTL/refresh can be added later if needed
            self._discovered = True
    
    async def call_asr_service(self, request_data: Dict[str, Any], api_key: Optional[str] = None) -> Dict[str, Any]:
        """Call ASR service for speech-to-text conversion."""
        await self._ensure_urls()
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
        await self._ensure_urls()
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
        await self._ensure_urls()
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
