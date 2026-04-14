"""
Model Management Service Client
Client for interacting with the model management service API
with caching support for efficient and scalable operations.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from urllib.parse import quote
import json

import httpx
from pydantic import BaseModel
from ai4icore_env import app_env

logger = logging.getLogger(__name__)


class ServiceInfo(BaseModel):
    """Service information model with embedded model data"""
    service_id: str
    model_id: str
    endpoint: Optional[str] = None
    inference_server_type: str = "triton"
    ssl_verify: bool = True
    api_key: Optional[str] = None
    triton_model: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    languages: Optional[List[Dict[str, Any]]] = None
    is_published: Optional[bool] = None
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
        cache_ttl_seconds: int = 300,
        timeout: float = 10.0,
    ):
        self.base_url = (base_url or app_env.model_management_service_url).rstrip("/")
        self.api_key = api_key
        self.cache_ttl_seconds = cache_ttl_seconds
        self.timeout = timeout
        self._cache: Dict[str, tuple[Any, datetime]] = {}
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_cache_key(self, key: str) -> str:
        return f"model_mgmt:{key}"

    def _get_from_cache(self, cache_key: str) -> Optional[Any]:
        if cache_key in self._cache:
            value, expiry = self._cache[cache_key]
            if datetime.now() < expiry:
                return value
            del self._cache[cache_key]
        return None

    def _set_cache(self, cache_key: str, value: Any):
        expiry = datetime.now() + timedelta(seconds=self.cache_ttl_seconds)
        self._cache[cache_key] = (value, expiry)

    def _get_headers(self, auth_headers: Optional[Dict[str, str]] = None, request: Optional[Any] = None) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}

        if request:
            try_it_header = getattr(request, "headers", {}).get("X-Try-It") or getattr(request, "headers", {}).get("x-try-it")
            if try_it_header:
                headers["X-Try-It"] = try_it_header

        if auth_headers:
            for key, value in auth_headers.items():
                key_lower = key.lower()
                if key_lower in ["authorization", "x-api-key", "x-auth-source", "x-try-it"]:
                    header_name = {
                        "authorization": "Authorization",
                        "x-api-key": "X-API-Key",
                        "x-auth-source": "X-Auth-Source",
                        "x-try-it": "X-Try-It",
                    }[key_lower]
                    headers[header_name] = value

        if "Authorization" not in headers and "X-API-Key" not in headers:
            if "X-Try-It" in headers:
                pass  # anonymous access via X-Try-It
            elif self.api_key:
                headers["X-API-Key"] = self.api_key
                headers["X-Auth-Source"] = "API_KEY"
        else:
            if "Authorization" in headers and "X-Auth-Source" not in headers:
                headers["X-Auth-Source"] = "AUTH_TOKEN"
            if "Authorization" not in headers and "X-API-Key" in headers and "X-Auth-Source" not in headers:
                headers["X-Auth-Source"] = "API_KEY"

        return headers

    async def list_services(
        self,
        use_cache: bool = True,
        redis_client=None,
        auth_headers: Optional[Dict[str, str]] = None,
        task_type: Optional[str] = None,
    ) -> List[ServiceInfo]:
        cache_key_suffix = f"list_services:{task_type}" if task_type else "list_services"
        cache_key = self._get_cache_key(cache_key_suffix)

        if use_cache and redis_client:
            try:
                cached = await redis_client.get(cache_key)
                if cached:
                    return [ServiceInfo(**item) for item in json.loads(cached)]
            except Exception:
                pass

        if use_cache:
            cached = self._get_from_cache(cache_key)
            if cached:
                return cached

        try:
            client = await self._get_client()
            url = f"{self.base_url}/api/v1/model-management/services"
            headers = self._get_headers(auth_headers)
            params = {"task_type": task_type} if task_type else {}
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()

            services = []
            for item in response.json():
                service_info = ServiceInfo(
                    service_id=item.get("serviceId", ""),
                    model_id=item.get("modelId", ""),
                    endpoint=item.get("endpoint"),
                    inference_server_type=item.get("inferenceServerType") or "triton",
                    ssl_verify=item.get("sslVerify", True),
                    api_key=item.get("api_key"),
                    triton_model="nmt",
                    name=item.get("name"),
                    description=item.get("serviceDescription"),
                    languages=item.get("languages", []),
                    model_task=item.get("task", {}),
                )
                services.append(service_info)

            if use_cache:
                if redis_client:
                    try:
                        await redis_client.setex(cache_key, self.cache_ttl_seconds, json.dumps([s.model_dump() for s in services]))
                    except Exception:
                        pass
                self._set_cache(cache_key, services)

            return services
        except Exception as e:
            logger.error(f"Error fetching services: {e}", exc_info=True)
            raise

    async def get_service(
        self,
        service_id: str,
        use_cache: bool = True,
        redis_client=None,
        auth_headers: Optional[Dict[str, str]] = None,
    ) -> Optional[ServiceInfo]:
        cache_key = self._get_cache_key(f"service:{service_id}")

        if use_cache and redis_client:
            try:
                cached = await redis_client.get(cache_key)
                if cached:
                    return ServiceInfo(**json.loads(cached))
            except Exception:
                pass

        if use_cache:
            cached = self._get_from_cache(cache_key)
            if cached:
                return cached

        try:
            client = await self._get_client()
            encoded_service_id = quote(service_id, safe="")
            url = f"{self.base_url}/api/v1/model-management/services/{encoded_service_id}"
            headers = self._get_headers(auth_headers)
            response = await client.post(url, headers=headers, json={"serviceId": service_id})

            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()

            model_data = data.get("model", {})
            languages = model_data.get("languages", []) if model_data else []

            service_info = ServiceInfo(
                service_id=data.get("serviceId", service_id),
                model_id=data.get("modelId", ""),
                endpoint=data.get("endpoint"),
                inference_server_type=data.get("inferenceServerType") or "triton",
                ssl_verify=data.get("sslVerify", True),
                api_key=data.get("api_key"),
                triton_model="nmt",
                name=data.get("name"),
                description=data.get("serviceDescription"),
                languages=languages,
                is_published=data.get("isPublished"),
                model_name=model_data.get("name") if model_data else None,
                model_description=model_data.get("description") if model_data else None,
                model_domain=model_data.get("domain", []) if model_data else None,
                model_task=model_data.get("task", {}) if model_data else None,
                model_inference_endpoint=model_data.get("inferenceEndPoint") if model_data else None,
            )

            if use_cache:
                if redis_client:
                    try:
                        await redis_client.setex(cache_key, self.cache_ttl_seconds, json.dumps(service_info.model_dump()))
                    except Exception:
                        pass
                self._set_cache(cache_key, service_info)

            return service_info
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
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
        auth_headers: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            client = await self._get_client()
            url = f"{self.base_url}/api/v1/model-management/experiments/select-variant"
            headers = self._get_headers(auth_headers)
            payload = {
                "task_type": task_type,
                "language": language,
                "request_id": request_id,
                "user_id": user_id,
                "service_id": service_id,
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
        auth_headers: Optional[Dict[str, str]] = None,
    ) -> None:
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

    def clear_cache(self, redis_client=None):
        self._cache.clear()
