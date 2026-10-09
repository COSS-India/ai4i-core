"""Async engines for the platform-core and auth databases.

The launcher calls init_databases() before a job runs and close_databases()
after it, so jobs only open sessions:

    async with platform_core_session() as session:
        ...
    async with auth_session() as session:
        ...

Engines connect lazily, so a job that never touches the auth DB never opens
a connection to it.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from ai4i_core.logging import get_logger
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bootstrap.config import get_settings

logger = get_logger(__name__)

_platform_core_engine: Optional[AsyncEngine] = None
_auth_engine: Optional[AsyncEngine] = None
_platform_core_session_factory: Optional[async_sessionmaker[AsyncSession]] = None
_auth_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def _engine(url: str) -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        url,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=True,
    )


def init_databases() -> None:
    global _platform_core_engine, _auth_engine, _platform_core_session_factory, _auth_session_factory
    if _platform_core_engine is not None:
        return
    settings = get_settings()
    _platform_core_engine = _engine(settings.get_platform_core_db_url())
    _auth_engine = _engine(settings.get_auth_db_url())
    _platform_core_session_factory = async_sessionmaker(_platform_core_engine, expire_on_commit=False)
    _auth_session_factory = async_sessionmaker(_auth_engine, expire_on_commit=False)
    logger.info(
        "Database engines initialised | platform_core_db=%s auth_db=%s",
        settings.PLATFORM_CORE_DB_NAME,
        settings.AUTH_SERVICE_DB_NAME or settings.AUTH_DB_NAME,
    )


async def close_databases() -> None:
    global _platform_core_engine, _auth_engine, _platform_core_session_factory, _auth_session_factory
    for engine in (_platform_core_engine, _auth_engine):
        if engine is not None:
            await engine.dispose()
    _platform_core_engine = _auth_engine = None
    _platform_core_session_factory = _auth_session_factory = None


def _require(factory: Optional[async_sessionmaker[AsyncSession]]) -> async_sessionmaker[AsyncSession]:
    if factory is None:
        raise RuntimeError("Databases not initialised; call init_databases() first")
    return factory


@asynccontextmanager
async def platform_core_session() -> AsyncIterator[AsyncSession]:
    async with _require(_platform_core_session_factory)() as session:
        yield session


@asynccontextmanager
async def auth_session() -> AsyncIterator[AsyncSession]:
    async with _require(_auth_session_factory)() as session:
        yield session
