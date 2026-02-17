"""
Tenant-aware database session dependency
"""
from fastapi import Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
import logging

from middleware.tenant_context import try_get_tenant_context

# Use structured logging if available
try:
    from ai4icore_logging import get_logger
    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


async def _get_shared_db_session(request: Request) -> AsyncSession:
    """
    Fallback to shared auth_db session (DATABASE_URL) when no tenant context exists.
    This is used for:
    - Normal users that are not tenants / tenant-users.
    - Requests where tenant resolution fails but we still want to serve from shared tables.
    """
    db_session_factory = getattr(request.app.state, "db_session_factory", None)
    if not db_session_factory:
        raise HTTPException(
            status_code=500,
            detail="Database session factory not initialized",
        )

    logger.info("Using shared auth_db session for ASR request (no tenant context).")
    return db_session_factory()


async def get_tenant_db_session(request: Request) -> AsyncSession:
    """
    Get database session for tenant-specific schema when the user is linked to a tenant.
    - If tenant context can be resolved → returns a session bound to the tenant schema in multi_tenant_db.
    - If no tenant context (normal user) → falls back to shared auth_db session.

    TenantMiddleware marks `/api/v1/nmt` requests with `needs_tenant_context = True`,
    so for those endpoints we always *try* tenant resolution first, then gracefully
    fall back to shared auth_db tables when the user is not a tenant/tenant-user.
    """
    # Check if tenant schema is already set (e.g., from JWT)
    schema_name = getattr(request.state, "tenant_schema", None)
    
    if schema_name:
        logger.info(f"Using tenant schema from request.state: {schema_name}")

    # If not set and this endpoint is tenant-aware, try to resolve tenant context
    if not schema_name and getattr(request.state, "needs_tenant_context", False):
        try:
            tenant_context = await try_get_tenant_context(request)
            if tenant_context:
                schema_name = tenant_context.get("schema_name")
                request.state.tenant_context = tenant_context
                request.state.tenant_schema = schema_name
                request.state.tenant_id = tenant_context.get("tenant_id")
                logger.info(
                    "Tenant context extracted for ASR: tenant_id=%s, schema=%s",
                    tenant_context.get("tenant_id"),
                    schema_name,
                )
            else:
                # No tenant association → use shared auth_db
                logger.debug("No tenant context found, using shared auth_db session")
                return await _get_shared_db_session(request)
        except Exception as e:
            logger.error("Failed to extract tenant context: %s", e, exc_info=True)
            # On errors resolving tenant, also fall back to shared auth_db to keep ASR functional
            return await _get_shared_db_session(request)

    # If schema still not set, fall back to shared auth_db
    if not schema_name:
        return await _get_shared_db_session(request)

    # Get tenant schema router from app state (set by lifespan)
    tenant_router = getattr(request.app.state, "tenant_schema_router", None)
    if not tenant_router:
        raise HTTPException(
            status_code=500,
            detail="Tenant schema router not initialized",
        )

    # Get session factory for this tenant's schema
    try:
        logger.info(f"Getting tenant session factory for schema: {schema_name}, router database_url: {tenant_router.database_url.split('@')[0] if hasattr(tenant_router, 'database_url') else 'unknown'}@***")
        factory = tenant_router.get_tenant_session_factory(schema_name)
        session = factory()
        
        # Verify which database the session is connected to
        result = await session.execute(text("SELECT current_database()"))
        db_name = result.scalar()
        logger.info(f"Tenant session connected to database: {db_name}")
    except ValueError as e:
        logger.error(f"Invalid schema name: {e}")
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_SCHEMA", "message": f"Invalid tenant schema: {str(e)}"},
        )

    # Ensure search_path is set (redundant but safe)
    await session.execute(text(f'SET search_path TO \"{schema_name}\", public'))
    
    # Verify search_path was set
    result = await session.execute(text("SHOW search_path"))
    search_path = result.scalar()
    logger.info(f"Tenant session search_path set to: {search_path}")

    return session
