"""
Database wiring for platform-core.

- Primary engine (`ai4iplatform_core`) — re-exported from the shared platform
  library; this is what every existing route + repository uses.
- Secondary engine (`auth_db`) — wrapped locally because only platform-core
  needs it (alert feature reads RBAC + tenant emails). Init is conditional on
  `settings.auth_db_name` being set, so the merged service starts cleanly
  whether or not alerting is configured.
"""

import logging
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ai4i_core.bootstrap.database import (  # noqa: F401
    init_database,
    close_database,
    get_db,
    get_engine,
)

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Secondary engine: auth_db ──

_auth_engine: Optional[AsyncEngine] = None
_auth_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def init_auth_database() -> None:
    """Initialise the secondary auth_db engine. No-op if not configured.

    Called from the FastAPI lifespan after `init_database`. Idempotent —
    safe to call multiple times.
    """
    global _auth_engine, _auth_session_factory
    if _auth_engine is not None:
        return
    url = settings.get_auth_db_url()
    if not url:
        logger.info("auth_db not configured (AUTH_DB_NAME unset) — skipping secondary engine init")
        return
    _auth_engine = create_async_engine(
        url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
    )
    _auth_session_factory = async_sessionmaker(
        _auth_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    logger.info("auth_db secondary engine initialised")


async def close_auth_database() -> None:
    """Dispose the secondary auth_db engine on shutdown. No-op if not initialised."""
    global _auth_engine, _auth_session_factory
    if _auth_engine is None:
        return
    await _auth_engine.dispose()
    _auth_engine = None
    _auth_session_factory = None
    logger.info("auth_db secondary engine disposed")


async def get_auth_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an AsyncSession bound to auth_db.

    Raises RuntimeError if auth_db wasn't initialised — caller (alert receiver
    service) must guard with `settings.auth_db_name` or rely on the alert
    feature being disabled.
    """
    if _auth_session_factory is None:
        raise RuntimeError(
            "auth_db is not initialised — set AUTH_DB_NAME and ensure "
            "init_auth_database() ran during lifespan startup"
        )
    async with _auth_session_factory() as session:
        yield session


async def get_auth_db_optional() -> AsyncIterator[Optional[AsyncSession]]:
    """Like `get_auth_db` but yields None when auth_db isn't configured.

    Lets the receiver service accept a missing auth_db and surface a clean
    error only when role/tenant resolution is actually requested.
    """
    if _auth_session_factory is None:
        yield None
        return
    async with _auth_session_factory() as session:
        yield session


# ── Session factories for non-request contexts (e.g. the alert sync loop) ──


def get_primary_session_factory() -> async_sessionmaker[AsyncSession]:
    """Build a session factory bound to the primary `ai4iplatform_core` engine.

    Use this in background tasks that run outside a request scope (where the
    `get_db` FastAPI dependency isn't available). Always open sessions with
    `async with factory() as session:` so they're cleanly closed.
    """
    return async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)


def get_auth_session_factory() -> Optional[async_sessionmaker[AsyncSession]]:
    """Return the auth_db session factory, or None if auth_db isn't configured."""
    return _auth_session_factory
