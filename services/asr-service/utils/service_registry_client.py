import os
import logging
import asyncio
from typing import Optional, Dict, Any

import httpx


logger = logging.getLogger(__name__)


class ServiceRegistryHttpClient:
    def __init__(self) -> None:
        base_url = os.getenv("CONFIG_SERVICE_URL", "http://config-service:8082")
        self._registry_base = base_url.rstrip("/") + "/api/v1/registry"
        self._max_retries = int(os.getenv("SERVICE_REGISTRY_MAX_RETRIES", "3"))
        self._retry_delay = float(os.getenv("SERVICE_REGISTRY_RETRY_DELAY", "2.0"))

    async def register(
        self,
        service_name: str,
        service_url: str,
        health_check_url: Optional[str],
        service_metadata: Optional[Dict[str, Any]] = None,
        request_timeout_s: float = 10.0,
    ) -> Optional[str]:
        payload = {
            "service_name": service_name,
            "service_url": service_url,
            "health_check_url": health_check_url,
            "service_metadata": service_metadata or {},
        }
        
        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(timeout=request_timeout_s) as client:
                    resp = await client.post(f"{self._registry_base}/register", json=payload)
                    resp.raise_for_status()
                    data = resp.json() or {}
                    instance_id = data.get("instance_id")
                    if instance_id:
                        logger.info(
                            "Service registry registration successful for %s (attempt %d/%d)",
                            service_name,
                            attempt + 1,
                            self._max_retries
                        )
                    return instance_id
            except httpx.ConnectError as e:
                if attempt < self._max_retries - 1:
                    delay = self._retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        "Service registry connection failed for %s (attempt %d/%d): %s. Retrying in %.1fs...",
                        service_name,
                        attempt + 1,
                        self._max_retries,
                        str(e),
                        delay
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Service registry registration failed for %s after %d attempts: %s",
                        service_name,
                        self._max_retries,
                        str(e)
                    )
            except httpx.HTTPStatusError as e:
                # Don't retry on HTTP errors (4xx, 5xx) - these are not transient
                logger.error(
                    "Service registry registration failed for %s with HTTP error: %s (status: %d)",
                    service_name,
                    str(e),
                    e.response.status_code
                )
                return None
            except Exception as e:
                if attempt < self._max_retries - 1:
                    delay = self._retry_delay * (2 ** attempt)
                    logger.warning(
                        "Service registry registration failed for %s (attempt %d/%d): %s. Retrying in %.1fs...",
                        service_name,
                        attempt + 1,
                        self._max_retries,
                        str(e),
                        delay
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Service registry registration failed for %s after %d attempts: %s",
                        service_name,
                        self._max_retries,
                        str(e)
                    )
        
        return None

    async def deregister(self, service_name: str, instance_id: str, request_timeout_s: float = 10.0) -> bool:
        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(timeout=request_timeout_s) as client:
                    resp = await client.post(
                        f"{self._registry_base}/deregister",
                        params={"service_name": service_name, "instance_id": instance_id},
                    )
                    resp.raise_for_status()
                    logger.info(
                        "Service registry deregistration successful for %s (instance: %s)",
                        service_name,
                        instance_id
                    )
                    return True
            except httpx.ConnectError as e:
                if attempt < self._max_retries - 1:
                    delay = self._retry_delay * (2 ** attempt)
                    logger.warning(
                        "Service registry deregistration connection failed (attempt %d/%d): %s. Retrying in %.1fs...",
                        attempt + 1,
                        self._max_retries,
                        str(e),
                        delay
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.warning("Service registry deregistration failed after %d attempts: %s", self._max_retries, str(e))
            except httpx.HTTPStatusError as e:
                # Don't retry on HTTP errors
                logger.warning(
                    "Service registry deregistration failed with HTTP error: %s (status: %d)",
                    str(e),
                    e.response.status_code
                )
                return False
            except Exception as e:
                if attempt < self._max_retries - 1:
                    delay = self._retry_delay * (2 ** attempt)
                    logger.warning(
                        "Service registry deregistration failed (attempt %d/%d): %s. Retrying in %.1fs...",
                        attempt + 1,
                        self._max_retries,
                        str(e),
                        delay
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.warning("Service registry deregistration failed after %d attempts: %s", self._max_retries, str(e))
        
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


