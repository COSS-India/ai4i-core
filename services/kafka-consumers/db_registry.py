from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ai4i_core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DatabaseEntry:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]


DB_REGISTRY: dict[str, DatabaseEntry] = {}


async def register_database(
    name: str,
    db_url: str,
    pool_size: int = 20,
    max_overflow: int = 10,
    echo: bool = False,
) -> None:
    """Create an engine + session factory for *name* and add it to DB_REGISTRY.

    Idempotent — skips silently if the name is already registered.
    """
    if name in DB_REGISTRY:
        logger.debug("Database %r already registered — skipping", name)
        return
    engine = create_async_engine(
        db_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        echo=echo,
    )
    DB_REGISTRY[name] = DatabaseEntry(
        engine=engine,
        session_factory=async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        ),
    )
    logger.info("Database %r registered (%s)", name, db_url.split("@")[-1])


class DatabaseRegistry:
    """Dispatches session requests to the correct engine by database name.

    Mirrors the shape of KafkaRegistry so the two registries stay conceptually
    consistent.
    """

    def __init__(self, registry: dict[str, DatabaseEntry]) -> None:
        self._registry = registry

    def names(self) -> list[str]:
        return list(self._registry.keys())

    @asynccontextmanager
    async def get_session(self, name: str) -> AsyncGenerator[AsyncSession, None]:
        """Yield an AsyncSession bound to the named database."""
        entry = self._registry.get(name)
        if entry is None:
            raise RuntimeError(
                f"Database {name!r} is not registered. "
                f"Available: {self.names()}"
            )
        async with entry.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    def get_engine(self, name: str) -> AsyncEngine:
        entry = self._registry.get(name)
        if entry is None:
            raise RuntimeError(f"Database {name!r} is not registered.")
        return entry.engine

    async def close_all(self) -> None:
        """Dispose every engine and clear the registry. Called on shutdown."""
        for name, entry in list(self._registry.items()):
            await entry.engine.dispose()
            logger.info("Database %r disposed", name)
        self._registry.clear()