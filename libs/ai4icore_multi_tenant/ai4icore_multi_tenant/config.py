"""
Multi-Tenant Plugin Configuration
"""
from typing import List, Optional

from ai4icore_env import app_env


class MultiTenantConfig:
    """Configuration for multi-tenant plugin."""

    def __init__(
        self,
        api_gateway_url: str = "http://api-gateway-service:8080",
        multi_tenant_db_url: Optional[str] = None,
        tenant_paths: Optional[List[str]] = None,
        enabled: bool = True,
    ):
        self.api_gateway_url = api_gateway_url
        self.multi_tenant_db_url = multi_tenant_db_url
        self.tenant_paths = tenant_paths or ["/api/v1"]
        self.enabled = enabled

    @classmethod
    def from_env(cls) -> "MultiTenantConfig":
        """Load configuration from environment variables."""
        api_gateway_url = app_env.api_gateway_url
        multi_tenant_db_url = app_env.get_multi_tenant_db_url()
        tenant_paths_str = app_env.tenant_paths or "/api/v1"
        tenant_paths = [p.strip() for p in tenant_paths_str.split(",") if p.strip()]
        enabled = app_env.multi_tenant_enabled

        return cls(
            api_gateway_url=api_gateway_url,
            multi_tenant_db_url=multi_tenant_db_url,
            tenant_paths=tenant_paths if tenant_paths else ["/api/v1"],
            enabled=enabled,
        )
