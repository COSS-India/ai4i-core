"""
Multi-Tenant Plugin Configuration
"""
import os
from typing import List, Optional


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
        api_gateway_url = os.getenv("API_GATEWAY_URL", "http://api-gateway-service:8080")
        multi_tenant_db_url = os.getenv("MULTI_TENANT_DB_URL")
        tenant_paths_str = os.getenv("TENANT_PATHS", "/api/v1")
        tenant_paths = [p.strip() for p in tenant_paths_str.split(",") if p.strip()]
        enabled = os.getenv("MULTI_TENANT_ENABLED", "true").lower() == "true"

        return cls(
            api_gateway_url=api_gateway_url,
            multi_tenant_db_url=multi_tenant_db_url,
            tenant_paths=tenant_paths if tenant_paths else ["/api/v1"],
            enabled=enabled,
        )
