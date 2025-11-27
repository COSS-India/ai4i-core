import os
import logging
from typing import Optional, Dict, Any

import httpx


logger = logging.getLogger(__name__)


class ServiceRegistryHttpClient:
    def __init__(self) -> None:
        base_url = os.getenv("CONFIG_SERVICE_URL", "http://config-service:8082")
        self._registry_base = base_url.rstrip("/") + "/api/v1/registry"

    async def register(
        self,
        service_name: str,
        service_url: str,
        health_check_url: Optional[str],
        service_metadata: Optional[Dict[str, Any]] = None,
        request_timeout_s: float = 5.0,
    ) -> Optional[str]:
        payload = {
            "service_name": service_name,
            "service_url": service_url,
            "health_check_url": health_check_url,
            "service_metadata": service_metadata or {},
        }
        try:
            async with httpx.AsyncClient(timeout=request_timeout_s) as client:
                resp = await client.post(f"{self._registry_base}/register", json=payload)
            resp.raise_for_status()
            data = resp.json() or {}
            return data.get("instance_id")
        except Exception as e:
            logger.warning("Service registry registration failed: %s", e)
            return None

    async def deregister(self, service_name: str, instance_id: str, request_timeout_s: float = 5.0) -> bool:
        try:
            async with httpx.AsyncClient(timeout=request_timeout_s) as client:
                resp = await client.post(
                    f"{self._registry_base}/deregister",
                    params={"service_name": service_name, "instance_id": instance_id},
                )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning("Service registry deregistration failed: %s", e)
            return False

    async def discover_url(self, service_name: str, request_timeout_s: float = 3.0) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=request_timeout_s) as client:
                resp = await client.get(f"{self._registry_base}/services/{service_name}/url")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json() or {}
            return data.get("url")
        except Exception as e:
            logger.warning("Service discovery failed for %s: %s", service_name, e)
            return None


