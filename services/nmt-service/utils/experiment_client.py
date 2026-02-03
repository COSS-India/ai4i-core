"""
Experiment Client for A/B Testing
Client to resolve which service variant to use based on active experiments.
"""

import logging
import os
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ExperimentResolution:
    """Result of variant resolution"""
    service_id: Optional[str]  # None if no experiment active
    variant: str  # "control", "treatment", or "default"
    experiment_name: Optional[str]
    experiment_id: Optional[str]


class ExperimentClient:
    """
    Client for resolving A/B experiment variants.
    
    Called before routing inference requests to determine which 
    service/model to use based on active experiments.
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 2.0,  # Fast timeout - don't block inference
        cache_ttl_seconds: int = 60
    ):
        """
        Initialize experiment client.
        
        Args:
            base_url: Model Management Service URL
            timeout: Request timeout (keep low to not block inference)
            cache_ttl_seconds: How long to cache "no experiment" results
        """
        self.base_url = base_url or os.getenv(
            "MODEL_MANAGEMENT_SERVICE_URL",
            "http://model-management-service:8091"
        )
        self.base_url = self.base_url.rstrip("/")
        self.timeout = timeout
        self.cache_ttl_seconds = cache_ttl_seconds
        
        # Simple in-memory cache for "no experiment" results
        # Avoids hitting Model Management on every request when no experiments
        self._no_experiment_cache: Dict[str, datetime] = {}
        
        # HTTP client (will be created lazily)
        self._client: Optional[httpx.AsyncClient] = None
    
    def _get_or_create_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client (lazy initialization)"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            )
        return self._client
    
    async def close(self):
        """Close HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def resolve_variant(
        self,
        task_type: str,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        request_id: Optional[str] = None,
        auth_headers: Optional[Dict[str, str]] = None
    ) -> ExperimentResolution:
        """
        Resolve which service variant to use for this request.
        
        Args:
            task_type: Task type (nmt, asr, tts, etc.)
            user_id: User ID for sticky assignment
            tenant_id: Tenant ID for sticky assignment (fallback)
            request_id: Request ID (fallback if no user/tenant)
            auth_headers: Auth headers to forward
            
        Returns:
            ExperimentResolution with service_id, variant, and experiment info.
            service_id is None if no experiment is active.
        """
        # Check "no experiment" cache first
        cache_key = f"no_exp:{task_type}"
        if cache_key in self._no_experiment_cache:
            expires_at = self._no_experiment_cache[cache_key]
            if datetime.now() < expires_at:
                logger.debug(f"Cache hit: no experiment for task_type={task_type}")
                return ExperimentResolution(
                    service_id=None,
                    variant="default",
                    experiment_name=None,
                    experiment_id=None
                )
            else:
                # Expired
                del self._no_experiment_cache[cache_key]
        
        try:
            client = self._get_or_create_client()
            
            # Build request parameters
            params = {"task_type": task_type}
            if user_id:
                params["user_id"] = user_id
            if tenant_id:
                params["tenant_id"] = tenant_id
            if request_id:
                params["request_id"] = request_id
            
            # Build headers
            headers = {}
            if auth_headers:
                for key, value in auth_headers.items():
                    if key.lower() in ["authorization", "x-api-key", "x-auth-source"]:
                        headers[key] = value
            
            url = f"{self.base_url}/experiments/resolve/variant"
            logger.debug(f"Resolving variant: {url} params={params}")
            
            response = await client.get(url, params=params, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                service_id = data.get("service_id") or None
                variant = data.get("variant", "default")
                experiment_name = data.get("experiment_name")
                experiment_id = data.get("experiment_id")
                
                # Cache "no experiment" result
                if not service_id or variant == "default":
                    self._no_experiment_cache[cache_key] = datetime.now() + timedelta(
                        seconds=self.cache_ttl_seconds
                    )
                    logger.debug(f"No active experiment for task_type={task_type}")
                else:
                    logger.info(
                        f"Experiment resolved: task_type={task_type} "
                        f"experiment={experiment_name} variant={variant} "
                        f"service_id={service_id[:16]}..."
                    )
                
                return ExperimentResolution(
                    service_id=service_id if service_id else None,
                    variant=variant,
                    experiment_name=experiment_name,
                    experiment_id=experiment_id
                )
            else:
                logger.warning(
                    f"Experiment resolution returned status {response.status_code}: {response.text}"
                )
                
        except httpx.TimeoutException:
            logger.warning(f"Experiment resolution timed out for task_type={task_type}")
        except Exception as e:
            logger.warning(f"Experiment resolution failed for task_type={task_type}: {e}")
        
        # Return default on any error (fail-safe: don't block inference)
        return ExperimentResolution(
            service_id=None,
            variant="default",
            experiment_name=None,
            experiment_id=None
        )
    
    def clear_cache(self):
        """Clear the no-experiment cache"""
        self._no_experiment_cache.clear()
        logger.info("Experiment client cache cleared")
