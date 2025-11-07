"""
Configuration Client
Client for fetching configurations from the Config Service
"""

import os
import logging
from typing import Optional, Dict, Any, List
import httpx
import asyncio


logger = logging.getLogger(__name__)


class ConfigurationClient:
    """Client for fetching configurations from Config Service
    
    Note: All configuration keys must be in UPPERCASE format (e.g., REDIS_HOST, DATABASE_URL)
    """
    
    def __init__(self) -> None:
        base_url = os.getenv("CONFIG_SERVICE_URL", "http://config-service:8082")
        self._config_base = base_url.rstrip("/") + "/api/v1/config"
        self._environment = os.getenv("ENVIRONMENT", "development")
        self._service_name = os.getenv("SERVICE_NAME", "nmt-service")
    
    @staticmethod
    def _normalize_key(key: str) -> str:
        """Normalize configuration key to UPPERCASE format"""
        return key.upper()
    
    async def get_config(
        self,
        key: str,
        environment: Optional[str] = None,
        service_name: Optional[str] = None,
        request_timeout_s: float = 3.0,
    ) -> Optional[str]:
        """
        Get a single configuration value by key
        
        Args:
            key: Configuration key (will be normalized to UPPERCASE)
            environment: Environment name (defaults to ENVIRONMENT env var)
            service_name: Service name (defaults to SERVICE_NAME env var)
            request_timeout_s: Request timeout in seconds
            
        Returns:
            Configuration value or None if not found
        """
        key = self._normalize_key(key)
        env = environment or self._environment
        service = service_name or self._service_name
        
        try:
            async with httpx.AsyncClient() as client:
                async with asyncio.timeout(request_timeout_s):
                    resp = await client.get(
                        f"{self._config_base}/{key}",
                        params={
                            "environment": env,
                            "service_name": service,
                        }
                    )
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                data = resp.json() or {}
                return data.get("value")
        except Exception as e:
            logger.warning("Failed to fetch config %s: %s", key, e)
            return None
    
    async def get_configs(
        self,
        keys: List[str],
        environment: Optional[str] = None,
        service_name: Optional[str] = None,
        request_timeout_s: float = 5.0,
    ) -> Dict[str, Optional[str]]:
        """
        Get multiple configuration values by keys (bulk fetch)
        
        Args:
            keys: List of configuration keys (will be normalized to UPPERCASE)
            environment: Environment name (defaults to ENVIRONMENT env var)
            service_name: Service name (defaults to SERVICE_NAME env var)
            request_timeout_s: Request timeout in seconds
            
        Returns:
            Dictionary mapping keys to values (None if not found)
        """
        # Normalize all keys to uppercase
        keys = [self._normalize_key(k) for k in keys]
        env = environment or self._environment
        service = service_name or self._service_name
        
        try:
            async with httpx.AsyncClient() as client:
                async with asyncio.timeout(request_timeout_s):
                    resp = await client.post(
                        f"{self._config_base}/bulk",
                        json={
                            "environment": env,
                            "service_name": service,
                            "keys": keys,
                        }
                    )
                resp.raise_for_status()
                data = resp.json() or {}
                # Response format: {"key1": {"value": "val1"}, "key2": {"value": "val2"}}
                result = {}
                for key in keys:
                    if key in data and isinstance(data[key], dict):
                        result[key] = data[key].get("value")
                    else:
                        result[key] = None
                return result
        except Exception as e:
            logger.warning("Failed to bulk fetch configs: %s", e)
            # Return None for all keys on error
            return dict.fromkeys(keys, None)
    
    async def get_all_configs(
        self,
        environment: Optional[str] = None,
        service_name: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        request_timeout_s: float = 5.0,
    ) -> Dict[str, str]:
        """
        Get all configurations for the service
        
        Args:
            environment: Environment name (defaults to ENVIRONMENT env var)
            service_name: Service name (defaults to SERVICE_NAME env var)
            limit: Maximum number of configs to return
            offset: Pagination offset
            request_timeout_s: Request timeout in seconds
            
        Returns:
            Dictionary mapping keys to values
        """
        env = environment or self._environment
        service = service_name or self._service_name
        
        try:
            async with httpx.AsyncClient() as client:
                async with asyncio.timeout(request_timeout_s):
                    resp = await client.get(
                        f"{self._config_base}/",
                        params={
                            "environment": env,
                            "service_name": service,
                            "limit": limit,
                            "offset": offset,
                        }
                    )
                resp.raise_for_status()
                data = resp.json() or {}
                items = data.get("items", [])
                result = {}
                for item in items:
                    if isinstance(item, dict):
                        result[item.get("key")] = item.get("value")
                return result
        except Exception as e:
            logger.warning("Failed to fetch all configs: %s", e)
            return {}

