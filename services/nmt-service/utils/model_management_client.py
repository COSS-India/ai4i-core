"""
Model Management Service Client
Client for interacting with the model management service API
with caching support for efficient and scalable operations
"""

import logging
import os
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import json

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ServiceInfo(BaseModel):
    """Service information model with embedded model data"""
    service_id: str
    model_id: str
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    triton_model: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    languages: Optional[List[Dict[str, Any]]] = None
    is_published: Optional[bool] = None
    # Model information extracted from service response
    model_name: Optional[str] = None
    model_description: Optional[str] = None
    model_domain: Optional[List[str]] = None
    model_task: Optional[Dict[str, Any]] = None
    model_inference_endpoint: Optional[Dict[str, Any]] = None


class ModelManagementClient:
    """Client for model management service with caching"""
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        cache_ttl_seconds: int = 300,  # 5 minutes default cache
        timeout: float = 10.0
    ):
        """
        Initialize model management service client
        
        Args:
            base_url: Base URL of model management service
            api_key: API key for authentication (if required)
            cache_ttl_seconds: Cache TTL in seconds
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or os.getenv(
            "MODEL_MANAGEMENT_SERVICE_URL",
            "http://model-management-service:8091"
        )
        # Ensure base_url doesn't end with /
        self.base_url = self.base_url.rstrip("/")
        self.api_key = api_key
        self.cache_ttl_seconds = cache_ttl_seconds
        self.timeout = timeout
        
        # In-memory cache (fallback if Redis not available)
        self._cache: Dict[str, tuple[Any, datetime]] = {}
        
        # HTTP client with connection pooling
        self._client: Optional[httpx.AsyncClient] = None
        
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with connection pooling"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
            )
        return self._client
    
    async def close(self):
        """Close HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    def _get_cache_key(self, key: str) -> str:
        """Generate cache key"""
        return f"model_mgmt:{key}"
    
    def _get_from_cache(self, cache_key: str) -> Optional[Any]:
        """Get value from in-memory cache (synchronous method)"""
        if cache_key in self._cache:
            value, expiry = self._cache[cache_key]
            if datetime.now() < expiry:
                return value
            else:
                # Expired, remove from cache
                del self._cache[cache_key]
        return None
    
    def _set_cache(self, cache_key: str, value: Any):
        """Set value in in-memory cache"""
        expiry = datetime.now() + timedelta(seconds=self.cache_ttl_seconds)
        self._cache[cache_key] = (value, expiry)
    
    def _get_headers(self, auth_headers: Optional[Dict[str, str]] = None, request: Optional[Any] = None) -> Dict[str, str]:
        """Get request headers with authentication
        
        Args:
            auth_headers: Optional dict of auth headers from incoming request (Authorization, X-API-Key, etc.)
            request: Optional FastAPI Request object to extract X-Try-It header
        """
        headers = {"Content-Type": "application/json"}
        
        # Forward X-Try-It header if present (allows anonymous access in Model Management)
        if request:
            try_it_header = getattr(request, "headers", {}).get("X-Try-It") or getattr(request, "headers", {}).get("x-try-it")
            if try_it_header:
                headers["X-Try-It"] = try_it_header
                logger.info("Forwarding X-Try-It header to Model Management for anonymous access")
        
        # Use auth headers from incoming request if provided (preferred)
        if auth_headers:
            logger.info(f"Processing auth_headers in _get_headers: {list(auth_headers.keys())}")
            # Forward all auth-related headers and special headers like X-Try-It
            for key, value in auth_headers.items():
                key_lower = key.lower()
                # Forward Authorization, X-API-Key, X-Auth-Source, and X-Try-It headers
                if key_lower in ["authorization", "x-api-key", "x-auth-source", "x-try-it"]:
                    # Use proper header case
                    header_name = "Authorization" if key_lower == "authorization" else \
                                 "X-API-Key" if key_lower == "x-api-key" else \
                                 "X-Auth-Source" if key_lower == "x-auth-source" else \
                                 "X-Try-It" if key_lower == "x-try-it" else key
                    headers[header_name] = value
                    logger.info(f"Added {header_name} header to request")
        else:
            logger.warning("No auth_headers provided to _get_headers")
        
        # If no auth headers provided, use fallback API key if available (for try-it anonymous requests)
        # But if X-Try-It header is present, Model Management will allow anonymous access
        if "Authorization" not in headers and "X-API-Key" not in headers:
            if "X-Try-It" in headers:
                logger.info("X-Try-It header present - Model Management will allow anonymous access")
            elif self.api_key:
                headers["X-API-Key"] = self.api_key
                headers["X-Auth-Source"] = "API_KEY"
                logger.info("Using fallback API key for Model Management request (no auth headers provided)")
            else:
                logger.warning("No authentication headers will be sent to model management service!")
        else:
            # If Authorization is present but X-Auth-Source is missing, assume AUTH_TOKEN
            if "Authorization" in headers and "X-Auth-Source" not in headers:
                headers["X-Auth-Source"] = "AUTH_TOKEN"
            # If only X-API-Key is present, mark source as API_KEY
            if "Authorization" not in headers and "X-API-Key" in headers and "X-Auth-Source" not in headers:
                headers["X-Auth-Source"] = "API_KEY"
        
        return headers
    
    async def list_services(
        self,
        use_cache: bool = True,
        redis_client = None,
        auth_headers: Optional[Dict[str, str]] = None,
        task_type: Optional[str] = None
    ) -> List[ServiceInfo]:
        """
        List all services from model management service
        
        Args:
            use_cache: Whether to use cache
            redis_client: Optional Redis client for distributed caching
            auth_headers: Optional auth headers from incoming request
            task_type: Optional task type filter (e.g., "nmt")
            
        Returns:
            List of ServiceInfo objects
        """
        # Include task_type in cache key to cache different task types separately
        cache_key_suffix = f"list_services"
        if task_type:
            cache_key_suffix = f"list_services:{task_type}"
        cache_key = self._get_cache_key(cache_key_suffix)
        
        # Try Redis cache first if available
        if use_cache and redis_client:
            try:
                cached = await redis_client.get(cache_key)
                if cached:
                    logger.debug("Cache hit for list_services (Redis)")
                    data = json.loads(cached)
                    return [ServiceInfo(**item) for item in data]
            except Exception as e:
                # Cache failures are non-critical - log at debug level to avoid noise
                logger.debug(f"Redis cache read failed: {e}")
        
        # Try in-memory cache
        if use_cache:
            cached = self._get_from_cache(cache_key)
            if cached:
                logger.debug("Cache hit for list_services (memory)")
                return cached
        
        # Fetch from API
        try:
            client = await self._get_client()
            url = f"{self.base_url}/api/v1/model-management/services"
            logger.info(f"About to call _get_headers with auth_headers: {auth_headers is not None}, keys: {list(auth_headers.keys()) if auth_headers else 'None'}")
            headers = self._get_headers(auth_headers)
            logger.info(f"After _get_headers, headers dict has keys: {list(headers.keys())}")
            
            # Add task_type as query parameter if provided
            params = {}
            if task_type:
                params["task_type"] = task_type
            
            logger.info(f"Fetching services from {url} with params: {params}")
            logger.info(f"Request headers keys: {list(headers.keys())}")
            logger.info(f"Authorization header: {'present' if 'Authorization' in headers else 'missing'}")
            logger.info(f"X-API-Key header: {'present' if 'X-API-Key' in headers else 'missing'}")
            if 'Authorization' in headers:
                logger.info(f"Authorization value (first 50 chars): {headers['Authorization'][:50]}...")
            if 'X-API-Key' in headers:
                logger.info(f"X-API-Key value (first 50 chars): {headers['X-API-Key'][:50]}...")
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            services = []
            
            for item in data:
                # Extract triton endpoint and model name from service data
                endpoint = item.get("endpoint")
                api_key = item.get("api_key")
                
                # Try to extract triton model name from inference endpoint
                # This might be in the model's inferenceEndPoint
                triton_model = "nmt"  # Default
                
                # Extract model information from service response
                # ServiceListResponse includes task and languages from model
                task = item.get("task", {})
                languages = item.get("languages", [])
                
                service_info = ServiceInfo(
                    service_id=item.get("serviceId", ""),
                    model_id=item.get("modelId", ""),
                    endpoint=endpoint,
                    api_key=api_key,
                    triton_model=triton_model,
                    name=item.get("name"),
                    description=item.get("serviceDescription"),
                    languages=languages,
                    model_task=task,
                    # Model name and description would come from view_service endpoint
                    # For list, we'll leave them None and fetch when needed
                )
                services.append(service_info)
            
            # Cache the result
            if use_cache:
                # Cache in Redis if available
                if redis_client:
                    try:
                        cache_data = [s.model_dump() for s in services]
                        await redis_client.setex(
                            cache_key,
                            self.cache_ttl_seconds,
                            json.dumps(cache_data)
                        )
                    except Exception as e:
                        # Cache failures are non-critical - log at debug level to avoid noise
                        logger.debug(f"Redis cache write failed: {e}")
                
                # Cache in memory
                self._set_cache(cache_key, services)
            
            logger.info(f"Fetched {len(services)} services from model management service")
            return services
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error(
                    f"Authentication failed (401) when fetching services from model management service. "
                    f"Please ensure the request includes valid Authorization or X-API-Key headers. "
                    f"Response: {e.response.text}"
                )
            else:
                logger.error(f"HTTP error fetching services: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Error fetching services: {e}", exc_info=True)
            raise
    
    async def get_service(
        self,
        service_id: str,
        use_cache: bool = True,
        redis_client = None,
        auth_headers: Optional[Dict[str, str]] = None
    ) -> Optional[ServiceInfo]:
        """
        Get service details by service ID
        
        Args:
            service_id: Service ID to fetch
            use_cache: Whether to use cache
            redis_client: Optional Redis client for distributed caching
            
        Returns:
            ServiceInfo object or None if not found
        """
        cache_key = self._get_cache_key(f"service:{service_id}")
        
        # Try Redis cache first if available
        if use_cache and redis_client:
            try:
                cached = await redis_client.get(cache_key)
                if cached:
                    logger.debug(f"Cache hit for service {service_id} (Redis)")
                    data = json.loads(cached)
                    return ServiceInfo(**data)
            except Exception as e:
                # Cache failures are non-critical - log at debug level to avoid noise
                logger.debug(f"Redis cache read failed: {e}")
        
        # Try in-memory cache
        if use_cache:
            cached = self._get_from_cache(cache_key)
            if cached:
                logger.debug(f"Cache hit for service {service_id} (memory)")
                return cached
        
        # Fetch from API
        try:
            client = await self._get_client()
            url = f"{self.base_url}/api/v1/model-management/services/{service_id}"
            headers = self._get_headers(auth_headers)
            payload = {"serviceId": service_id}
            
            logger.debug(f"Fetching service {service_id} from {url}")
            response = await client.post(url, headers=headers, json=payload)
            
            if response.status_code == 404:
                return None
            
            response.raise_for_status()
            data = response.json()
            
            # Extract triton endpoint and model name
            endpoint = data.get("endpoint")
            api_key = data.get("api_key")
            triton_model = "nmt"  # Default
            
            # Extract model information from service response
            # ServiceViewResponse includes full model object
            model_data = data.get("model", {})
            languages = model_data.get("languages", []) if model_data else []
            
            service_info = ServiceInfo(
                service_id=data.get("serviceId", service_id),
                model_id=data.get("modelId", ""),
                endpoint=endpoint,
                api_key=api_key,
                triton_model=triton_model,
                name=data.get("name"),
                description=data.get("serviceDescription"),
                languages=languages,
                is_published=data.get("isPublished"),
                # Extract model information from embedded model object
                model_name=model_data.get("name") if model_data else None,
                model_description=model_data.get("description") if model_data else None,
                model_domain=model_data.get("domain", []) if model_data else None,
                model_task=model_data.get("task", {}) if model_data else None,
                model_inference_endpoint=model_data.get("inferenceEndPoint") if model_data else None
            )
            
            # Cache the result
            if use_cache:
                # Cache in Redis if available
                if redis_client:
                    try:
                        await redis_client.setex(
                            cache_key,
                            self.cache_ttl_seconds,
                            json.dumps(service_info.model_dump())
                        )
                    except Exception as e:
                        # Cache failures are non-critical - log at debug level to avoid noise
                        logger.debug(f"Redis cache write failed: {e}")
                
                # Cache in memory
                self._set_cache(cache_key, service_info)
            
            return service_info
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            elif e.response.status_code == 401:
                logger.error(
                    f"Authentication failed (401) when fetching service {service_id} from model management service. "
                    f"Please ensure the request includes valid Authorization or X-API-Key headers. "
                    f"Response: {e.response.text}"
                )
            else:
                logger.error(f"HTTP error fetching service {service_id}: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Error fetching service {service_id}: {e}", exc_info=True)
            raise
    
    
    async def select_experiment_variant(
        self,
        task_type: str,
        language: Optional[str] = None,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        service_id: Optional[str] = None,
        auth_headers: Optional[Dict[str, str]] = None
    ) -> Optional[Dict[str, Any]]:
        """Select an experiment variant for A/B testing. Returns variant dict or None."""
        try:
            client = await self._get_client()
            url = f"{self.base_url}/api/v1/model-management/experiments/select-variant"
            headers = self._get_headers(auth_headers)
            payload = {
                "task_type": task_type,
                "language": language,
                "request_id": request_id,
                "user_id": user_id,
                "service_id": service_id
            }
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                return None
            data = response.json()
            return data if data.get("is_experiment") else None
        except Exception as e:
            logger.debug("select_experiment_variant failed: %s", e)
            return None

    async def track_experiment_metric(
        self,
        experiment_id: str,
        variant_id: str,
        success: bool,
        latency_ms: int,
        custom_metrics: Optional[Dict[str, Any]] = None,
        auth_headers: Optional[Dict[str, str]] = None
    ) -> None:
        """Track one request's metrics for an experiment variant (best-effort)."""
        try:
            client = await self._get_client()
            url = f"{self.base_url}/api/v1/model-management/experiments/track-metric"
            headers = self._get_headers(auth_headers)
            payload = {
                "experiment_id": experiment_id,
                "variant_id": variant_id,
                "success": success,
                "latency_ms": latency_ms,
                "custom_metrics": custom_metrics or {},
            }
            await client.post(url, headers=headers, json=payload)
        except Exception as e:
            logger.warning("track_experiment_metric failed: %s", e)

    def clear_cache(self, redis_client = None):
        """Clear all caches"""
        self._cache.clear()
        logger.info("In-memory cache cleared")
        
        if redis_client:
            # Note: This would require pattern matching which Redis supports
            # For now, we'll just log that cache should be cleared manually
            logger.info("Redis cache should be cleared manually if needed")

