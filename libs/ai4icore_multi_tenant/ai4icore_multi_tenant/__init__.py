"""
AI4ICore Multi-Tenant Plugin
Shared tenant context, schema routing, and DB session for AI4ICore services.
"""

from .config import MultiTenantConfig
from .plugin import MultiTenantPlugin
from .tenant_context import (
    try_get_tenant_context,
    get_tenant_context,
    resolve_tenant_from_jwt,
    resolve_tenant_from_user_id,
)
from .models import Tenant, TenantUser, TenantDBBase
from .enforce_tenant_and_service_checks import enforce_tenant_and_service_checks
from .tenant_schema_router import TenantSchemaRouter
from .tenant_middleware import TenantMiddleware
from .tenant_db_dependency import get_tenant_db_session_factory

__all__ = [
    "MultiTenantConfig",
    "MultiTenantPlugin",
    "try_get_tenant_context",
    "get_tenant_context",
    "resolve_tenant_from_jwt",
    "resolve_tenant_from_user_id",
    "enforce_tenant_and_service_checks",
    "TenantSchemaRouter",
    "TenantMiddleware",
    "get_tenant_db_session_factory",
    "Tenant",
    "TenantUser",
    "TenantDBBase",
]
