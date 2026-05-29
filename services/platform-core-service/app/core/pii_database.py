"""
PII database — async SQLAlchemy engine and session factory for the
ai4i_platform DB (the PII service's own database, kept separate from
the platform-core primary DB).

Mirrors the pattern in ai4icore_core.bootstrap.database so the rest of
the codebase stays consistent; just a different engine/session pair.
"""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)

_pii_engine: AsyncEngine | None = None
_pii_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_pii_database(
    db_url: str,
    pool_size: int = 10,
    max_overflow: int = 5,
    echo: bool = False,
) -> None:
    """Create the PII async engine and session factory. Called during app startup."""
    global _pii_engine, _pii_session_factory

    logger.info("Connecting to PII database: %s", db_url.split("@")[-1])

    _pii_engine = create_async_engine(
        db_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        echo=echo,
    )
    _pii_session_factory = async_sessionmaker(
        bind=_pii_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    logger.info("PII database engine initialized.")


async def close_pii_database() -> None:
    """Dispose of the PII engine. Called during app shutdown."""
    global _pii_engine, _pii_session_factory
    if _pii_engine:
        await _pii_engine.dispose()
        logger.info("PII database engine disposed.")
    _pii_engine = None
    _pii_session_factory = None


async def get_pii_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async PII DB session."""
    if _pii_session_factory is None:
        raise RuntimeError("PII database not initialized. Call init_pii_database() first.")
    async with _pii_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def get_pii_engine() -> AsyncEngine:
    """Return the PII engine (for instrumentation / health checks)."""
    if _pii_engine is None:
        raise RuntimeError("PII database not initialized.")
    return _pii_engine
