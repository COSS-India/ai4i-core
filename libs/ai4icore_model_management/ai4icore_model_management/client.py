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
    
    def _get_headers(self, auth_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Get request headers with authentication
        
        Args:
            auth_headers: Optional dict of auth headers from incoming request (Authorization, X-API-Key, etc.)
        """
        headers = {"Content-Type": "application/json"}
        
        # Use auth headers from incoming request if provided (preferred)
        if auth_headers:
            logger.debug(f"Processing auth_headers in _get_headers: {list(auth_headers.keys())}")
            # Forward all auth-related headers
            for key, value in auth_headers.items():
                key_lower = key.lower()
                # Forward Authorization, X-API-Key, and X-Auth-Source headers
                if key_lower in ["authorization", "x-api-key", "x-auth-source"]:
                    # Use proper header case
                    header_name = "Authorization" if key_lower == "authorization" else \
                                 "X-API-Key" if key_lower == "x-api-key" else \
                                 "X-Auth-Source" if key_lower == "x-auth-source" else key
                    headers[header_name] = value
                    logger.debug(f"Added {header_name} header to request")
        else:
            logger.debug("No auth_headers provided to _get_headers")
        
        # Do not inject fallback API keys here; rely on forwarded request auth only
        if "Authorization" not in headers and "X-API-Key" not in headers:
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
            task_type: Optional task type filter (e.g., "transliteration")
            
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
                logger.warning(f"Redis cache read failed: {e}")
        
        # Try in-memory cache
        if use_cache:
            cached = self._get_from_cache(cache_key)
            if cached:
                logger.debug("Cache hit for list_services (memory)")
                return cached
        
        # Fetch from API
        try:
            client = await self._get_client()
            url = f"{self.base_url}/services/details/list_services"
            logger.debug(f"About to call _get_headers with auth_headers: {auth_headers is not None}")
            headers = self._get_headers(auth_headers)
            
            # Add task_type as query parameter if provided
            params = {}
            if task_type:
                params["task_type"] = task_type
            
            logger.info(f"Fetching services from {url} with params: {params}")
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            services = []
            
            for item in data:
                # Extract triton endpoint and model name from service data
                endpoint = item.get("endpoint")
                api_key = item.get("api_key")
                
                # Try to extract triton model name from inference endpoint
                # Default to "transliteration" for this service
                triton_model = "transliteration"
                
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
                        logger.warning(f"Redis cache write failed: {e}")
                
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
            auth_headers: Optional auth headers from incoming request
            
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
                logger.warning(f"Redis cache read failed: {e}")
        
        # Try in-memory cache
        if use_cache:
            cached = self._get_from_cache(cache_key)
            if cached:
                logger.debug(f"Cache hit for service {service_id} (memory)")
                return cached
        
        # Fetch from API
        try:
            client = await self._get_client()
            url = f"{self.base_url}/services/details/view_service"
            headers = self._get_headers(auth_headers)
            payload = {"serviceId": service_id}
            
            logger.debug(f"Fetching service {service_id} from {url}")
            response = await client.post(url, headers=headers, json=payload)
            
            if response.status_code == 404:
                logger.warning(f"Service {service_id} not found in model management service")
                return None
            
            response.raise_for_status()
            data = response.json()
            
            # Extract triton endpoint and model name
            endpoint = data.get("endpoint")
            api_key = data.get("api_key")
            
            # Default to "transliteration" for this service
            triton_model = "transliteration"
            
            # Try to extract model name from model's inferenceEndPoint if available
            model_data = data.get("model", {})
            if model_data:
                inference_endpoint = model_data.get("inferenceEndPoint", {})
                if isinstance(inference_endpoint, dict):
                    # Check if there's a model name in the inference endpoint config
                    model_name_from_endpoint = inference_endpoint.get("modelName")
                    if model_name_from_endpoint:
                        triton_model = model_name_from_endpoint
            
            # Extract model information from service response
            # ServiceViewResponse includes full model object
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
                        logger.warning(f"Redis cache write failed: {e}")
                
                # Cache in memory
                self._set_cache(cache_key, service_info)
            
            logger.info(f"Successfully fetched service {service_id} from model management service")
            return service_info
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Service {service_id} not found (404)")
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
    
    
    def clear_cache(self, redis_client = None):
        """Clear all caches"""
        self._cache.clear()
        logger.info("In-memory cache cleared")
        
        if redis_client:
            # Note: This would require pattern matching which Redis supports
            # For now, we'll just log that cache should be cleared manually
            logger.info("Redis cache should be cleared manually if needed")

