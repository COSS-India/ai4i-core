"""
Tenant-aware database session dependency
"""
from fastapi import Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import logging

from ai4icore_env import app_env

from .tenant_context import try_get_tenant_context

logger = logging.getLogger(__name__)

DEFAULT_API_GATEWAY_URL = app_env.api_gateway_url


async def _get_shared_db_session(request: Request) -> AsyncSession:
    """
    Fallback to shared auth_db session when no tenant context exists.
    """
    db_session_factory = getattr(request.app.state, "db_session_factory", None)
    if not db_session_factory:
        raise HTTPException(
            status_code=500,
            detail="Database session factory not initialized",
        )

    logger.debug("Using shared auth_db session (no tenant context).")
    return db_session_factory()


def get_tenant_db_session_factory(api_gateway_url: str = None):
    """
    Returns a dependency function that gets the tenant-aware database session.
    Use with FastAPI Depends(): Depends(get_tenant_db_session_factory())
    """

    _api_gateway_url = api_gateway_url or DEFAULT_API_GATEWAY_URL

    async def get_tenant_db_session(request: Request) -> AsyncSession:
        """
        Get database session for tenant-specific schema when the user is linked to a tenant.
        Falls back to shared auth_db session when no tenant context.
        """
        schema_name = getattr(request.state, "tenant_schema", None)

        if not schema_name and getattr(request.state, "needs_tenant_context", False):
            try:
                tenant_context = await try_get_tenant_context(request, _api_gateway_url)
                if tenant_context:
                    schema_name = tenant_context.get("schema_name")
                    request.state.tenant_context = tenant_context
                    request.state.tenant_schema = schema_name
                    request.state.tenant_id = tenant_context.get("tenant_id")
                    logger.debug(
                        "Tenant context extracted: tenant_id=%s, schema=%s",
                        tenant_context.get("tenant_id"),
                        schema_name,
                    )
                else:
                    return await _get_shared_db_session(request)
            except Exception as e:
                logger.error("Failed to extract tenant context: %s", e, exc_info=True)
                return await _get_shared_db_session(request)

        if not schema_name:
            return await _get_shared_db_session(request)

        tenant_router = getattr(request.app.state, "tenant_schema_router", None)
        if not tenant_router:
            raise HTTPException(
                status_code=500,
                detail="Tenant schema router not initialized",
            )

        try:
            factory = tenant_router.get_tenant_session_factory(schema_name)
            session = factory()
        except ValueError as e:
            logger.error(f"Invalid schema name: {e}")
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_SCHEMA", "message": f"Invalid tenant schema: {str(e)}"},
            )

        await session.execute(text(f'SET search_path TO "{schema_name}", public'))
        return session

    return get_tenant_db_session
