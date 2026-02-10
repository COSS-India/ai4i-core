"""
Model Resolution Middleware
FastAPI middleware for automatic serviceId → endpoint + model_name resolution
"""

import json
import logging
import time
import uuid
from typing import Optional, Dict, Tuple, Any

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .client import ModelManagementClient, ServiceInfo
from .triton_client import TritonClient

logger = logging.getLogger(__name__)


def extract_auth_headers(request: Request) -> Dict[str, str]:
    """Extract authentication headers from incoming request"""
    auth_headers: Dict[str, str] = {}
    
    # Check Authorization header (case-insensitive)
    authorization = request.headers.get("Authorization") or request.headers.get("authorization")
    if authorization:
        auth_headers["Authorization"] = authorization
    
    # Check X-API-Key header (case-insensitive)
    x_api_key = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
    if x_api_key:
        auth_headers["X-API-Key"] = x_api_key
    
    # Check X-Auth-Source header
    x_auth_source = request.headers.get("X-Auth-Source") or request.headers.get("x-auth-source")
    if x_auth_source:
        auth_headers["X-Auth-Source"] = x_auth_source
    
    return auth_headers


def extract_service_id_from_body(body: bytes) -> Optional[str]:
    """Extract serviceId from request body (JSON)"""
    try:
        data = json.loads(body.decode('utf-8'))
        # Try common patterns: config.serviceId, serviceId, config.service_id
        if isinstance(data, dict):
            if "config" in data and isinstance(data["config"], dict):
                service_id = data["config"].get("serviceId") or data["config"].get("service_id")
                if service_id:
                    logger.debug(f"Extracted serviceId from config: {service_id}")
                return service_id
            service_id = data.get("serviceId") or data.get("service_id")
            if service_id:
                logger.debug(f"Extracted serviceId from root: {service_id}")
            return service_id
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError) as e:
        logger.debug(f"Failed to extract serviceId from body: {e}")
    return None


def extract_task_type_from_path(path: str) -> Optional[str]:
    """Extract task type from URL path (e.g. /api/v1/asr/inference -> asr)."""
    parts = path.strip("/").split("/")
    # Expect ... /api/v1/<task_type>/... or ... /<task_type>/...
    for i, p in enumerate(parts):
        if p in ("asr", "nmt", "tts", "ocr", "ner", "transliteration", "llm", "pipeline"):
            return p
    return None


def extract_language_from_body(body: bytes) -> Optional[str]:
    """Extract primary language from request body (config.language.sourceLanguage or similar)."""
    try:
        data = json.loads(body.decode('utf-8'))
        if not isinstance(data, dict):
            return None
        config = data.get("config") or {}
        if not isinstance(config, dict):
            return None
        lang = config.get("language")
        if isinstance(lang, dict):
            return lang.get("sourceLanguage") or lang.get("targetLanguage") or lang.get("language")
        if isinstance(lang, str):
            return lang
        return None
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        return None


class ModelResolutionMiddleware(BaseHTTPMiddleware):
    """Middleware that resolves serviceId to Triton endpoint and model_name"""
    
    def __init__(
        self,
        app,
        model_management_client: ModelManagementClient,
        redis_client = None,
        cache_ttl_seconds: int = 300,
        default_triton_endpoint: Optional[str] = None,
        default_triton_api_key: Optional[str] = None,
        enabled_paths: list[str] = None
    ):
        """
        Initialize middleware
        
        Args:
            app: FastAPI application
            model_management_client: Model Management client instance
            redis_client: Optional Redis client for shared caching
            cache_ttl_seconds: Cache TTL in seconds
            default_triton_endpoint: Default Triton endpoint (fallback)
            default_triton_api_key: Default Triton API key
            enabled_paths: List of URL path prefixes where middleware should run
        """
        super().__init__(app)
        self.model_management_client = model_management_client
        self.redis_client = redis_client
        self.cache_ttl_seconds = cache_ttl_seconds
        self.default_triton_endpoint = default_triton_endpoint
        self.default_triton_api_key = default_triton_api_key
        self.enabled_paths = enabled_paths or ["/api/v1"]
        
        # In-memory caches
        self._service_info_cache: Dict[str, Tuple[ServiceInfo, float]] = {}
        self._service_registry_cache: Dict[str, Tuple[str, str, float]] = {}  # serviceId -> (endpoint, model_name, expires_at)
        self._triton_clients: Dict[str, Tuple[TritonClient, str, float]] = {}  # serviceId -> (client, endpoint, expires_at)
        self.cache_prefix = "model_mgmt:triton"
    
    def _should_process(self, path: str) -> bool:
        """Check if middleware should process this path"""
        return any(path.startswith(prefix) for prefix in self.enabled_paths)
    
    async def _get_service_info(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> Optional[ServiceInfo]:
        """Get service info from model management service with caching"""
        # Check cache first
        cached = self._service_info_cache.get(service_id)
        if cached:
            service_info, expires_at = cached
            if expires_at > time.time():
                return service_info
            self._service_info_cache.pop(service_id, None)
        
        # Fetch from model management service
        try:
            service_info = await self.model_management_client.get_service(
                service_id,
                use_cache=True,
                redis_client=self.redis_client,
                auth_headers=auth_headers
            )
            if service_info:
                expires_at = time.time() + self.cache_ttl_seconds
                self._service_info_cache[service_id] = (service_info, expires_at)
                # Also update registry cache
                if service_info.endpoint:
                    endpoint, model_name = self._extract_triton_metadata(service_info, service_id)
                    self._service_registry_cache[service_id] = (endpoint, model_name, expires_at)
            return service_info
        except Exception as e:
            logger.error(
                f"Failed to fetch service info for {service_id} from model management service: {e}. "
                "Service resolution failed - some services require Model Management database entries."
            )
            return None
    
    def _extract_triton_metadata(self, service_info: ServiceInfo, service_id: str = None) -> Tuple[str, str]:
        """Extract normalized Triton endpoint and model name from service info"""
        endpoint = service_info.endpoint.replace("http://", "").replace("https://", "") if service_info.endpoint else ""
        model_name = None

        # Try to infer model name from model inference endpoint metadata (highest priority)
        if service_info.model_inference_endpoint:
            # Check inside schema FIRST (most specific location for Triton model name)
            schema = service_info.model_inference_endpoint.get("schema", {})
            if isinstance(schema, dict):
                model_name = (
                    schema.get("model_name")
                    or schema.get("modelName")
                    or schema.get("name")
                )
            
            # If not in schema, check top level of inferenceEndPoint
            if not model_name:
                model_name = (
                    service_info.model_inference_endpoint.get("model_name")
                    or service_info.model_inference_endpoint.get("modelName")
                    or service_info.model_inference_endpoint.get("model")
                )
        
        # Fall back to triton_model from task.type (least specific)
        if not model_name:
            model_name = service_info.triton_model
        
        # If still no model name, try to extract from service_id
        if not model_name and service_id:
            parts = service_id.split("/")
            if len(parts) > 1:
                model_part = parts[-1]
            else:
                model_part = service_id
            
            if "--" in model_part:
                model_name = model_part.split("--")[0]
            else:
                model_name = model_part
        
        # Final fallback
        if not model_name:
            model_name = "unknown"
            logger.warning(
                f"Could not determine Triton model name for service {service_id}. "
                f"Using placeholder 'unknown'."
            )
        
        return endpoint, model_name
    
    async def _get_service_registry_entry(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> Optional[Tuple[str, str]]:
        """Get service registry entry (endpoint, model_name) for service_id"""
        # Check local cache first
        cached = self._service_registry_cache.get(service_id)
        if cached:
            endpoint, model_name, expires_at = cached
            if expires_at > time.time():
                return endpoint, model_name
            self._service_registry_cache.pop(service_id, None)

        # Check Redis cache (shared across instances)
        redis_entry = await self._get_registry_from_redis(service_id)
        if redis_entry:
            endpoint, model_name = redis_entry
            expires_at = time.time() + self.cache_ttl_seconds
            self._service_registry_cache[service_id] = (endpoint, model_name, expires_at)
            return endpoint, model_name
        
        # Fetch from model management service
        service_info = await self._get_service_info(service_id, auth_headers)
        if service_info and service_info.endpoint:
            endpoint, model_name = self._extract_triton_metadata(service_info, service_id)
            expires_at = time.time() + self.cache_ttl_seconds
            self._service_registry_cache[service_id] = (endpoint, model_name, expires_at)
            await self._set_registry_in_redis(service_id, endpoint, model_name)
            return endpoint, model_name
        
        return None
    
    async def _get_registry_from_redis(self, service_id: str) -> Optional[Tuple[str, str]]:
        """Read shared registry entry from Redis"""
        if not self.redis_client:
            return None
        try:
            cache_key = f"{self.cache_prefix}:registry:{service_id}"
            cached = await self.redis_client.get(cache_key)
            if cached:
                data = json.loads(cached)
                endpoint = data.get("endpoint")
                model_name = data.get("model_name")
                if endpoint and model_name:
                    return endpoint, model_name
        except Exception as e:
            logger.warning(f"Redis read failed for service {service_id}: {e}")
        return None

    async def _set_registry_in_redis(self, service_id: str, endpoint: str, model_name: str):
        """Write shared registry entry to Redis"""
        if not self.redis_client:
            return
        try:
            cache_key = f"{self.cache_prefix}:registry:{service_id}"
            payload = json.dumps({"endpoint": endpoint, "model_name": model_name})
            await self.redis_client.setex(cache_key, self.cache_ttl_seconds, payload)
        except Exception as e:
            logger.warning(f"Redis write failed for service {service_id}: {e}")
    
    async def _resolve_service(self, service_id: str, auth_headers: Dict[str, str]) -> Tuple[Optional[str], Optional[str], Optional[TritonClient]]:
        """Resolve serviceId to endpoint, model_name, and Triton client"""
        # Get endpoint and model name
        service_entry = await self._get_service_registry_entry(service_id, auth_headers)
        if service_entry:
            endpoint, model_name = service_entry
            
            # Get or create Triton client
            cached_client = self._triton_clients.get(service_id)
            if cached_client:
                client, cached_endpoint, expires_at = cached_client
                if expires_at > time.time() and cached_endpoint == endpoint:
                    return endpoint, model_name, client
                self._triton_clients.pop(service_id, None)
            
            # Create new client
            client = TritonClient(triton_url=endpoint, api_key=self.default_triton_api_key)
            expires_at = time.time() + self.cache_ttl_seconds
            self._triton_clients[service_id] = (client, endpoint, expires_at)
            return endpoint, model_name, client

        # No fallback: if Model Management cannot resolve the serviceId, return no endpoint/model/client.
        # Routers are responsible for returning clear HTTP 4xx/5xx errors in this case.
        logger.error(f"Model Management did not resolve serviceId: {service_id} and no default endpoint is allowed")
        return None, None, None
        
    async def dispatch(self, request: Request, call_next):
        """Process request and resolve service if needed. Supports A/B testing via select-variant."""
        start_time = time.time()
        try:
            # Only process enabled paths
            if not self._should_process(request.url.path):
                logger.debug(f"Middleware skipping path: {request.url.path} (not in enabled_paths)")
                return await call_next(request)
            
            logger.debug(f"Model Resolution Middleware processing: {request.method} {request.url.path}")
            
            # For POST requests, try to extract serviceId from body
            service_id = None
            body = None
            if request.method == "POST":
                # Check if body was already read by another middleware (e.g., Observability)
                body_was_cached = hasattr(request, '_body') and request._body is not None
                
                if body_was_cached:
                    body = request._body
                else:
                    body = await request.body()
                
                service_id = extract_service_id_from_body(body)
                
                if service_id:
                    logger.info(f"Extracted serviceId from request: {service_id}")
                else:
                    logger.warning(f"No serviceId found in request body for {request.url.path}")
            
            # A/B testing: check for experiment variant and optionally override service_id
            if service_id and body is not None:
                task_type = extract_task_type_from_path(request.url.path)
                language = extract_language_from_body(body)
                # request_id and user_id for variant hashing (when user_id present, same user => same variant)
                request_id = (
                    request.headers.get("X-Request-ID") or request.headers.get("x-request-id")
                    or request.headers.get("X-Correlation-ID") or request.headers.get("x-correlation-id")
                ) or str(uuid.uuid4())
                # User ID for consistent variant per user (from auth middleware or gateway header)
                user_id = (
                    getattr(request.state, "user_id", None)
                    or request.headers.get("X-User-Id") or request.headers.get("x-user-id")
                )
                if user_id is not None:
                    user_id = str(user_id)
                if task_type:
                    try:
                        variant = await self.model_management_client.select_experiment_variant(
                            task_type=task_type,
                            language=language,
                            request_id=request_id,
                            user_id=user_id,
                            service_id=service_id,
                            auth_headers=extract_auth_headers(request)
                        )
                        if variant and variant.get("service_id"):
                            logger.info(
                                f"A/B experiment active: using variant {variant.get('variant_name')} "
                                f"(service_id={variant.get('service_id')})"
                            )
                            request.state.service_id = variant["service_id"]
                            request.state.experiment_info = variant
                            if variant.get("endpoint") and (variant.get("model_id") or variant.get("model_name")):
                                request.state.triton_endpoint = (
                                    variant["endpoint"].replace("http://", "").replace("https://", "")
                                )
                                request.state.triton_model_name = (
                                    variant.get("model_id") or variant.get("model_name") or "unknown"
                                )
                                if variant.get("api_key") is not None:
                                    request.state.triton_api_key = variant.get("api_key")
                                response = await call_next(request)
                                await self._track_experiment_metric(request, response, start_time)
                                return response
                            service_id = variant["service_id"]
                    except Exception as e:
                        logger.debug("A/B select-variant failed, using default service: %s", e)
            
            # If we found a serviceId, resolve it (normal path or variant service_id)
            if service_id:
                logger.info(f"Resolving serviceId: {service_id} via Model Management")
                auth_headers = extract_auth_headers(request)
                endpoint, model_name, triton_client = await self._resolve_service(service_id, auth_headers)
                
                request.state.service_id = service_id
                if endpoint:
                    request.state.triton_endpoint = endpoint
                    logger.info(f"Resolved endpoint: {endpoint} for serviceId: {service_id}")
                else:
                    logger.error(f"Failed to resolve endpoint for serviceId: {service_id}")
                    request.state.model_management_error = "Endpoint not found"
                if model_name:
                    request.state.triton_model_name = model_name
                    logger.info(f"Resolved model_name: {model_name} for serviceId: {service_id}")
                else:
                    logger.error(f"Failed to resolve model_name for serviceId: {service_id}")
                    request.state.model_management_error = "Model name not found"
                if triton_client:
                    request.state.triton_client = triton_client
            else:
                logger.debug("No serviceId found, skipping Model Management resolution")
            
            response = await call_next(request)
            if getattr(request.state, "experiment_info", None):
                await self._track_experiment_metric(request, response, start_time)
            return response
            
        except HTTPException as e:
            logger.warning(f"HTTPException in Model Resolution Middleware: {e.detail}")
            raise
        except Exception as e:
            logger.error(f"Critical error in Model Resolution Middleware: {e}", exc_info=True)
            raise
    
    async def _track_experiment_metric(self, request: Request, response: Response, start_time: float) -> None:
        """Track experiment metric after response (best-effort)."""
        info = getattr(request.state, "experiment_info", None)
        if not info or not info.get("experiment_id") or not info.get("variant_id"):
            return
        try:
            status = getattr(response, "status_code", 500)
            success = 200 <= status < 400
            latency_ms = int((time.time() - start_time) * 1000)
            await self.model_management_client.track_experiment_metric(
                experiment_id=info["experiment_id"],
                variant_id=info["variant_id"],
                success=success,
                latency_ms=latency_ms,
                auth_headers=extract_auth_headers(request)
            )
        except Exception as e:
            logger.debug("Experiment metric tracking failed: %s", e)