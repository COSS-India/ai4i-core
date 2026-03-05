"""
Multi-Tenant Plugin - One-line registration for FastAPI apps
"""
import logging
from typing import Optional, Callable, Any

from fastapi import FastAPI

from .config import MultiTenantConfig
from .tenant_schema_router import TenantSchemaRouter
from .tenant_middleware import TenantMiddleware
from .tenant_db_dependency import get_tenant_db_session_factory

logger = logging.getLogger(__name__)


class MultiTenantPlugin:
    """Plugin for multi-tenant integration in FastAPI apps."""

    def __init__(self, config: Optional[MultiTenantConfig] = None):
        self.config = config or MultiTenantConfig.from_env()
        self.tenant_schema_router: Optional[TenantSchemaRouter] = None

    def register_plugin(
        self,
        app: FastAPI,
        db_session_factory: Optional[Any] = None,
        multi_tenant_db_url: Optional[str] = None,
    ) -> None:
        """
        Register multi-tenant plugin with FastAPI app.

        Args:
            app: FastAPI application instance
            db_session_factory: Shared auth_db session factory (from app.state or lifespan)
            multi_tenant_db_url: URL for multi-tenant database (defaults to config or DATABASE_URL)
        """
        if not self.config.enabled:
            logger.info("Multi-tenant plugin is disabled")
            return

        db_url = multi_tenant_db_url or self.config.multi_tenant_db_url
        if not db_url:
            logger.warning(
                "MULTI_TENANT_DB_URL not configured. "
                "Tenant schema routing may fall back to shared DB."
            )
            db_url = getattr(app.state, "db_url_fallback", None)
            if not db_url:
                logger.warning("Cannot initialize TenantSchemaRouter without database URL")

        if db_url:
            self.tenant_schema_router = TenantSchemaRouter(database_url=db_url)
            app.state.tenant_schema_router = self.tenant_schema_router
            logger.info("Tenant schema router initialized")

        if db_session_factory:
            app.state.db_session_factory = db_session_factory

        app.add_middleware(TenantMiddleware, tenant_paths=self.config.tenant_paths)
        logger.info(
            "Multi-tenant middleware registered for paths: %s", self.config.tenant_paths
        )

    def get_tenant_db_session_dependency(self):
        """
        Returns a FastAPI dependency for get_tenant_db_session.
        Use: Depends(plugin.get_tenant_db_session_dependency())
        """
        return get_tenant_db_session_factory(self.config.api_gateway_url)

    async def close(self) -> None:
        """Cleanup resources"""
        if self.tenant_schema_router:
            await self.tenant_schema_router.close_all()
            self.tenant_schema_router = None
