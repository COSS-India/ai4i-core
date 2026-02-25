"""
Tenant-aware database session dependency
"""
from fastapi import Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional, AsyncGenerator
import logging

from middleware.tenant_context import try_get_tenant_context

logger = logging.getLogger(__name__)


async def _get_shared_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    Fallback to shared auth_db session (DATABASE_URL) when no tenant context exists.
    This is used for:
    - Normal users that are not tenants / tenant-users.
    - Requests where tenant resolution fails but we still want to serve from shared tables.
    
    This is a generator function that yields the session so FastAPI can properly manage it.
    """
    db_session_factory = getattr(request.app.state, "db_session_factory", None)
    if not db_session_factory:
        raise HTTPException(
            status_code=500,
            detail="Database session factory not initialized",
        )

    logger.debug("Using shared auth_db session for TTS request (no tenant context).")
    session = db_session_factory()
    try:
        yield session
    except GeneratorExit:
        # Generator is being closed - this is normal cleanup
        raise
    except BaseException:
        # Any exception thrown into generator - re-raise to stop generator properly
        raise
    finally:
        # Always close session in finally block
        if session is not None:
            try:
                await session.close()
            except Exception as cleanup_error:
                # Log but don't re-raise - cleanup errors shouldn't mask original errors
                logger.debug(f"Error closing shared session during cleanup: {cleanup_error}")
                pass


async def get_tenant_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    Get database session for tenant-specific schema when the user is linked to a tenant.
    - If tenant context can be resolved → returns a session bound to the tenant schema in multi_tenant_db.
    - If no tenant context (normal user) → falls back to shared auth_db session.

    TenantMiddleware marks `/api/v1/tts` requests with `needs_tenant_context = True`,
    so for those endpoints we always *try* tenant resolution first, then gracefully
    fall back to shared auth_db tables when the user is not a tenant/tenant-user.
    
    This is a generator function that yields the session so FastAPI can properly manage it.
    """
    # Check if tenant schema is already set (e.g., from JWT)
    schema_name = getattr(request.state, "tenant_schema", None)

    # If not set and this endpoint is tenant-aware, try to resolve tenant context
    if not schema_name and getattr(request.state, "needs_tenant_context", False):
        try:
            tenant_context = await try_get_tenant_context(request)
            if tenant_context:
                schema_name = tenant_context.get("schema_name")
                request.state.tenant_context = tenant_context
                request.state.tenant_schema = schema_name
                request.state.tenant_id = tenant_context.get("tenant_id")
                logger.debug(
                    "Tenant context extracted for TTS: tenant_id=%s, schema=%s",
                    tenant_context.get("tenant_id"),
                    schema_name,
                )
            else:
                # No tenant association → use shared auth_db
                schema_name = None  # Force fallback to shared session
        except Exception as e:
            logger.error("Failed to extract tenant context: %s", e, exc_info=True)
            # On errors resolving tenant, also fall back to shared auth_db to keep TTS functional
            schema_name = None  # Force fallback to shared session

    # If schema still not set, fall back to shared auth_db
    # Check for None, empty string, or any falsy value
    if not schema_name or schema_name is None:
        db_session_factory = getattr(request.app.state, "db_session_factory", None)
        if not db_session_factory:
            raise HTTPException(
                status_code=500,
                detail="Database session factory not initialized",
            )
        session = db_session_factory()
        try:
            yield session
        except GeneratorExit:
            # Generator is being closed - ensure session is closed
            if session is not None:
                try:
                    await session.close()
                except Exception:
                    pass
            raise
        except BaseException:
            # Any exception - close session and re-raise to stop generator
            if session is not None:
                try:
                    await session.close()
                except Exception:
                    pass
            raise
        # Normal completion - close session
        if session is not None:
            try:
                await session.close()
            except Exception:
                pass
        return  # Explicitly return to prevent further execution

    # Validate schema_name is not None before proceeding
    if schema_name is None or not schema_name.strip():
        logger.error(f"Invalid schema_name: {schema_name}")
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_SCHEMA", "message": "Invalid tenant schema: schema name cannot be None or empty"},
        )

    # Get tenant schema router from app state (set by lifespan)
    tenant_router = getattr(request.app.state, "tenant_schema_router", None)
    if not tenant_router:
        raise HTTPException(
            status_code=500,
            detail="Tenant schema router not initialized",
        )

    # Get session factory for this tenant's schema
    session = None
    try:
        factory = tenant_router.get_tenant_session_factory(schema_name)
        session = factory()
        
        # Ensure search_path is set (redundant but safe)
        # This can fail in production due to network latency/timeouts
        try:
            await session.execute(text(f'SET search_path TO \"{schema_name}\", public'))
        except Exception as db_error:
            logger.error(
                f"Failed to set search_path for schema {schema_name}: {db_error}",
                exc_info=True
            )
            # Don't close session here - let finally block handle it
            # Re-raise as HTTPException for proper error handling
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "DATABASE_ERROR",
                    "message": f"Database connection error: {str(db_error)}"
                }
            ) from db_error
        
        # Yield the session - FastAPI will manage lifecycle after this point
        # When an exception is thrown into the generator via athrow(), it will be raised at the yield point
        try:
            yield session
        except GeneratorExit:
            # Generator is being closed - ensure session is closed
            if session is not None:
                try:
                    await session.close()
                except Exception:
                    pass
            raise
        except BaseException:
            # Any exception - close session and re-raise to stop generator immediately
            if session is not None:
                try:
                    await session.close()
                except Exception:
                    pass
            raise
        # Normal completion - close session
        if session is not None:
            try:
                await session.close()
            except Exception:
                pass
    except HTTPException:
        # Re-raise HTTPExceptions (already properly formatted)
        raise
    except ValueError as e:
        logger.error(f"Invalid schema name: {e}")
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_SCHEMA", "message": f"Invalid tenant schema: {str(e)}"},
        )
