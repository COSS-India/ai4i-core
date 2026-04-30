"""
Tenant-aware database session dependency
"""
from fastapi import Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from sqlalchemy import select
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ai4icore_env import app_env

from .models import Tenant
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


def _get_multi_tenant_lookup_session_factory(request: Request) -> async_sessionmaker:
    """
    Build or reuse a session factory for querying multi-tenant metadata in public schema.
    """
    existing_factory = getattr(request.app.state, "multi_tenant_lookup_session_factory", None)
    if existing_factory:
        return existing_factory

    tenant_router = getattr(request.app.state, "tenant_schema_router", None)
    if not tenant_router or not getattr(tenant_router, "database_url", None):
        raise HTTPException(
            status_code=500,
            detail="Tenant schema router not initialized",
        )

    lookup_engine = create_async_engine(
        tenant_router.database_url,
        pool_size=5,
        max_overflow=5,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=3600,
        connect_args={
            "timeout": 30,
            "command_timeout": 30,
        },
    )
    lookup_factory = async_sessionmaker(
        lookup_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    request.app.state.multi_tenant_lookup_engine = lookup_engine
    request.app.state.multi_tenant_lookup_session_factory = lookup_factory
    return lookup_factory


async def _resolve_schema_name_from_tenant_id(
    request: Request, tenant_id: str
) -> Optional[str]:
    """
    Resolve schema name from tenant_id by querying the multi-tenant DB.
    """
    if not tenant_id:
        return None

    try:
        lookup_factory = _get_multi_tenant_lookup_session_factory(request)
        async with lookup_factory() as lookup_session:
            result = await lookup_session.execute(
                select(Tenant.schema_name).where(Tenant.tenant_id == tenant_id).limit(1)
            )
            schema_name = result.scalar_one_or_none()
            if schema_name:
                logger.debug(
                    "Resolved schema from tenant_id=%s -> schema=%s",
                    tenant_id,
                    schema_name,
                )
            else:
                logger.warning("No schema found for tenant_id=%s", tenant_id)
            return schema_name
    except Exception as e:
        logger.error(
            "Failed to resolve schema for tenant_id=%s: %s",
            tenant_id,
            e,
            exc_info=True,
        )
        return None


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
        tenant_id = getattr(request.state, "tenant_id", None)
        # Reuse schema cached in request state to avoid repeated DB lookups.
        schema_name = getattr(request.state, "tenant_schema", None)

        if getattr(request.state, "needs_tenant_context", False):
            try:
                tenant_context = await try_get_tenant_context(request, _api_gateway_url)
                if tenant_context:
                    tenant_id = tenant_context.get("tenant_id")
                    request.state.tenant_context = tenant_context
                    request.state.tenant_id = tenant_id
                    logger.debug(
                        "Tenant context extracted: tenant_id=%s",
                        tenant_id,
                    )
                else:
                    return await _get_shared_db_session(request)
            except Exception as e:
                logger.error("Failed to extract tenant context: %s", e, exc_info=True)
                return await _get_shared_db_session(request)

        if not schema_name and tenant_id:
            schema_name = await _resolve_schema_name_from_tenant_id(request, tenant_id)
            if schema_name:
                request.state.tenant_schema = schema_name

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
