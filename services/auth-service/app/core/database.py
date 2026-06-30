"""
Database — re-exports from shared ai4icore_bootstrap.
Auth-service uses the same DB infra as every other service.

Secondary engine (platform_core_db) is initialised only when
PLATFORM_CORE_DB_NAME is set, enabling read-only tier lookups
against the platform-core database without HTTP round-trips.
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


# ── Secondary engine: platform_core_db ──────────────────────────────────────

_platform_core_engine: Optional[AsyncEngine] = None
_platform_core_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def init_platform_core_database() -> None:
    """Initialise the read-only platform-core engine. No-op if not configured."""
    global _platform_core_engine, _platform_core_session_factory
    if _platform_core_engine is not None:
        return
    url = settings.get_platform_core_db_url()
    if not url:
        logger.info(
            "platform_core_db not configured (PLATFORM_CORE_DB_NAME unset) — "
            "tier_id will not appear in list-tenants responses"
        )
        return
    _platform_core_engine = create_async_engine(
        url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
    )
    _platform_core_session_factory = async_sessionmaker(
        _platform_core_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    logger.info("platform_core_db secondary engine initialised (db=%s)", settings.platform_core_db_name)


async def close_platform_core_database() -> None:
    """Dispose the platform-core engine on shutdown. No-op if not initialised."""
    global _platform_core_engine, _platform_core_session_factory
    if _platform_core_engine is None:
        return
    await _platform_core_engine.dispose()
    _platform_core_engine = None
    _platform_core_session_factory = None
    logger.info("platform_core_db secondary engine disposed")


async def get_platform_core_db() -> AsyncIterator[Optional[AsyncSession]]:
    """FastAPI dependency yielding an AsyncSession bound to platform_core_db.

    Yields None when PLATFORM_CORE_DB_NAME is not configured so that
    endpoints degrade gracefully (tier_id omitted) rather than failing.
    """
    if _platform_core_session_factory is None:
        yield None
        return
    async with _platform_core_session_factory() as session:
        yield session
