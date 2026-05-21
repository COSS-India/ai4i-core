"""
InferenceServerResolver for looking up Triton endpoints and model information.
Provides caching with Redis and in-memory cache for efficient server resolution.
"""

from typing import Any, Dict, Optional, Tuple
import logging
import time
import os

from utils import HTTPServiceClient, ServiceNotFoundError as HTTPServiceNotFoundError


logger = logging.getLogger(__name__)


class CacheEntry:
    """In-memory cache entry with TTL."""

    def __init__(self, value: Any, ttl_seconds: int):
        """
        Initialize cache entry.

        Args:
            value: Value to cache
            ttl_seconds: Time-to-live in seconds
        """
        self.value = value
        self.ttl_seconds = ttl_seconds
        self.created_at = time.time()

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return time.time() - self.created_at > self.ttl_seconds


class InferenceServerResolverError(Exception):
    """Base exception for resolver errors."""

    pass


class ServiceNotFoundError(InferenceServerResolverError):
    """Raised when service cannot be resolved."""

    pass


class InferenceServerResolver:
    """
    Resolver for finding Triton inference endpoints and model information.
    Maintains dual-layer cache (Redis + in-memory) for fast lookups.
    Supports both required and SMR-optional service_id patterns.
    """

    def __init__(self):
        """
        Initialize inference server resolver with in-memory caching only.
        """
        self._memory_cache: Dict[str, Any] = {}

    async def resolve_service(
        self,
        service_id: str,
    ) -> Dict[str, Any]:
        """
        Resolve inference service information.
        Returns model name and Triton endpoint for given service_id.
        Uses dual-layer cache for performance.

        Args:
            service_id: Service ID to resolve
            session_id: Optional session ID for tracing

        Returns:
            Dict with keys:
                - service_id: Service ID
                - model_name: Model name in Triton
                - triton_endpoint: Triton server URL
                - triton_api_key: Optional Triton API key

        Raises:
            ServiceNotFoundError: If service cannot be resolved
        """
        # Check cache
        cached = await self._get_from_cache(service_id)
        if cached:
            self._log_cache_hit(service_id, "cache")
            return cached
        
        # Query model management service
        try:
            service_info = await self._query_model_management_service(service_id)
            await self._cache_service_info(service_id, service_info)
            return service_info
        except ServiceNotFoundError:
            self._log_resolution_error(service_id, "Service not found in management service")
            raise

    async def resolve_smr_service(
        self,
        payload: Dict[str, Any],
        session_id: Optional[str] = None,
    ) -> str:
        """
        Resolve service_id via SmartModelRouter when not explicitly provided.
        Used for services that support SMR-optional routing (NMT, ASR, TTS).

        Args:
            payload: Request payload for SMR routing
            session_id: Optional session ID for tracing

        Returns:
            Resolved service_id

        Raises:
            ServiceNotFoundError: If SMR routing fails
        """
        # For now, return default service_id
        return "indictrans-v2-all"

    async def _get_from_cache(self, service_id: str) -> Optional[Dict[str, Any]]:
        """
        Get service information from dual-layer cache.
        Checks in-memory cache first, then Redis.

        Args:
            service_id: Service ID to lookup

        Returns:
            Service info dict or None if not found
        """
        # Check memory cache first
        if service_id in self._memory_cache:
            return self._memory_cache[service_id]
        return None

    async def _get_from_memory_cache(self, service_id: str) -> Optional[Dict[str, Any]]:
        """
        Get service information from in-memory cache.

        Args:
            service_id: Service ID to lookup

        Returns:
            Service info dict or None if not found/expired
        """
        return self._memory_cache.get(service_id)

    async def _query_model_management_service(
        self,
        service_id: str,
    ) -> Dict[str, Any]:
        """
        Fetch service details from the model management service.

        Args:
            service_id: Unique identifier for the registered model service.

        Returns:
            Service info dict containing name, endpoint, api_key, and adapter_config.

        Raises:
            ServiceNotFoundError: If the service is not found or the call fails.
        """
        model_management_url = os.getenv("MODEL_MANAGEMENT_SERVICE_URL")
        if not model_management_url:
            logger.error("MODEL_MANAGEMENT_SERVICE_URL not configured")
            raise ServiceNotFoundError(f"Service {service_id} not found: Model management service not configured")

        try:
            http_client = HTTPServiceClient(timeout=30)
            url = f"{model_management_url}/api/v1/model-management/services/{service_id}"
            # GET — this is a read-only service lookup, not a write operation
            service_info = await http_client.get_json(url)

            logger.debug(f"Resolved service {service_id}: {service_info}")
            return service_info
                
        except HTTPServiceNotFoundError as e:
            logger.error(f"Service {service_id} not found: {str(e)}")
            raise ServiceNotFoundError(f"Service {service_id} not found") from e
        except Exception as e:
            logger.error(f"Failed to query model management service: {str(e)}")
            raise ServiceNotFoundError(f"Service {service_id} not found: {str(e)}") from e

    async def _cache_service_info(
        self,
        service_id: str,
        service_info: Dict[str, Any],
    ) -> None:
        """
        Cache service information in both Redis and in-memory cache.

        Args:
            service_id: Service ID
            service_info: Service information to cache
        """
        await self._cache_to_memory(service_id, service_info)

    async def _cache_to_memory(
        self,
        service_id: str,
        service_info: Dict[str, Any],
    ) -> None:
        """
        Cache service information to in-memory cache.

        Args:
            service_id: Service ID
            service_info: Service information to cache
        """
        self._memory_cache[service_id] = service_info

    async def _query_database(
        self,
        service_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Query database directly for service configuration.
        Used as fallback when model management service is unavailable.

        Args:
            service_id: Service ID to query

        Returns:
            Service info dict or None if not found
        """
        return None

    def _format_cache_key(self, service_id: str) -> str:
        """
        Format Redis cache key for service info.

        Args:
            service_id: Service ID

        Returns:
            Formatted cache key
        """
        return f"service:{service_id}"

    def _log_cache_hit(self, service_id: str, cache_type: str) -> None:
        """
        Log cache hit for monitoring.

        Args:
            service_id: Service ID
            cache_type: Type of cache hit (memory, redis, db)
        """
        logger.debug(f"Cache hit for service {service_id} from {cache_type}")

    def _log_resolution_error(
        self,
        service_id: str,
        error_msg: str,
    ) -> None:
        """
        Log service resolution error.

        Args:
            service_id: Service ID that failed to resolve
            error_msg: Error message
        """
        logger.error(f"Failed to resolve service {service_id}: {error_msg}")

    async def clear_cache(self, service_id: Optional[str] = None) -> None:
        """
        Clear cache entries.

        Args:
            service_id: Optional specific service to clear, or all if None
        """
        if service_id:
            self._memory_cache.pop(service_id, None)
        else:
            self._memory_cache.clear()
