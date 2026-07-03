"""
Async SQLAlchemy engine, session factory, and get_db dependency.

Used by ALL microservices. No service-specific imports.
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

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_database(
    db_url: str,
    pool_size: int = 20,
    max_overflow: int = 10,
    echo: bool = False,
) -> None:
    """Create the async engine and session factory. Called during app startup."""
    global _engine, _session_factory

    logger.info("Connecting to database: %s", db_url.split("@")[-1])

    _engine = create_async_engine(
        db_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        echo=echo,
    )
    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    logger.info("Database engine initialized.")


async def close_database() -> None:
    """Dispose of the engine. Called during app shutdown."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        logger.info("Database engine disposed.")
    _engine = None
    _session_factory = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    async with _session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def get_engine() -> AsyncEngine:
    """Return the current engine (for Alembic / telemetry instrumentation)."""
    if _engine is None:
        raise RuntimeError("Database not initialized.")
    return _engine
