"""
HTTP client for interacting with the central service registry.

Usage:
    from ai4icore_service_base import ServiceRegistryClient

    client = ServiceRegistryClient(base_url="http://config-service:8080")
    instance_id = await client.register("nmt-service", "http://nmt:8089", "/health")
    await client.deregister("nmt-service", instance_id)
"""

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class ServiceRegistryClient:
    """Register, deregister, and discover services via the central registry."""

    def __init__(self, base_url: str) -> None:
        self._registry_base = base_url.rstrip("/") + "/api/v1/registry"

    async def register(
        self,
        service_name: str,
        service_url: str,
        health_check_url: Optional[str] = None,
        service_metadata: Optional[dict[str, Any]] = None,
        request_timeout_s: float = 5.0,
    ) -> Optional[str]:
        """Register a service instance. Returns instance_id on success, None on failure."""
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

    async def deregister(
        self,
        service_name: str,
        instance_id: str,
        request_timeout_s: float = 5.0,
    ) -> bool:
        """Deregister a service instance. Returns True on success."""
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

    async def discover_url(
        self, service_name: str, request_timeout_s: float = 3.0
    ) -> Optional[str]:
        """Look up the URL of a named service. Returns None if not found."""
        try:
            async with httpx.AsyncClient(timeout=request_timeout_s) as client:
                resp = await client.get(
                    f"{self._registry_base}/services/{service_name}/url"
                )
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                data = resp.json() or {}
                return data.get("url")
        except Exception as e:
            logger.warning("Service discovery failed for %s: %s", service_name, e)
            return None
