"""Process lifetime: the default database, named extra databases, Redis, and
signal handling.

This is the only place ai4i_core.bootstrap.init_database is called.  The library
holds exactly one engine and one sessionmaker in module globals and re-assigns
them WITHOUT disposing the previous pair, so a second init_database() silently
leaks a connection pool.  Extra databases go through the name-keyed registry
below, which generalises auth-service's single hardcoded secondary
(services/auth-service/app/core/database.py: init_platform_core_database /
close_platform_core_database / get_platform_core_db).

Naming note (§3.1): the local `bootstrap` package is not `ai4i_core.bootstrap`,
it wraps it.  The library is imported by its full path and the local package
relatively, so the distinction is visible at the import line.
"""
from __future__ import annotations

import asyncio
import signal
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from ai4i_core.bootstrap import (
    close_database,
    close_redis,
    get_engine,
    init_database,
    init_redis,
)
from ai4i_core.logging import get_logger
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bootstrap.config import get_db_settings, get_redis_settings

logger = get_logger(__name__)

_engines: dict[str, AsyncEngine] = {}
_session_factories: dict[str, async_sessionmaker[AsyncSession]] = {}
_default_factory: Optional[async_sessionmaker[AsyncSession]] = None


# ── the default connection + the cache ─────────────────────────────────────
@asynccontextmanager
async def infra(
    *,
    db_name: str,
    pool_size: int | None = None,
    max_overflow: int | None = None,
) -> AsyncIterator[None]:
    """Open the default database + Redis; close them and every named
    connection on the way out."""
    global _default_factory

    db = get_db_settings()
    rd = get_redis_settings()

    # init_database takes a URL, not a database name — the URL is built here
    # from DatabaseSettings so credentials are declared exactly once.
    await init_database(
        db_url=db.get_database_url(db_name),
        pool_size=pool_size if pool_size is not None else db.DB_POOL_SIZE,
        max_overflow=max_overflow if max_overflow is not None else db.DB_MAX_OVERFLOW,
    )
    logger.info("Database ready | db=%s host=%s", db_name, db.POSTGRES_HOST)
    try:
        # socket_timeout was never passed by the old main.py, leaving REDIS_TIMEOUT inert.
        await init_redis(rd.get_redis_url(), socket_timeout=rd.REDIS_TIMEOUT)
        logger.info("Redis ready | host=%s db=%d", rd.REDIS_HOST, rd.REDIS_DB)
        yield
    finally:
        _default_factory = None
        await close_all_databases()
        await close_database()
        await close_redis()
        logger.info("Infrastructure closed")


# ── named connections ──────────────────────────────────────────────────────
async def add_database(
    name: str,
    *,
    db_name: str | None = None,
    url: str | None = None,
    pool_size: int | None = None,
    max_overflow: int | None = None,
) -> None:
    """Open an additional connection under a caller-chosen key.

    Idempotent — a no-op if `name` is already open, so a consumer may call it
    from more than one code path.

    Give `db_name` for another database on the SAME Postgres instance (the URL
    is built from DatabaseSettings, so credentials are declared once); give
    `url` for a different instance with its own credentials.
    """
    if name in _engines:
        return
    if (db_name is None) == (url is None):
        raise ValueError("add_database requires exactly one of db_name or url")

    db = get_db_settings()
    engine = create_async_engine(
        url or db.get_database_url(db_name),
        pool_size=pool_size if pool_size is not None else db.DB_POOL_SIZE,
        max_overflow=max_overflow if max_overflow is not None else db.DB_MAX_OVERFLOW,
        pool_pre_ping=True,
    )
    _engines[name] = engine
    _session_factories[name] = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    logger.info("Named database opened | name=%s", name)


def get_engine_for(name: str) -> AsyncEngine:
    """The named engine, for text() execution outside a session."""
    try:
        return _engines[name]
    except KeyError:
        raise RuntimeError(
            f"database {name!r} was never opened — call add_database({name!r}, ...) first. "
            f"Open: {sorted(_engines)}"
        ) from None


async def close_database_connection(name: str) -> None:
    """Dispose one named engine.  No-op if absent.

    Named close_database_CONNECTION, not close_database: the latter is imported
    from ai4i_core.bootstrap and closes the DEFAULT connection.  Two functions
    one letter apart that close different things is exactly the collision the
    ManagedConsumer wrapper naming avoids.
    """
    engine = _engines.pop(name, None)
    _session_factories.pop(name, None)
    if engine is not None:
        await engine.dispose()
        logger.info("Named database closed | name=%s", name)


async def close_all_databases() -> None:
    """Dispose every named engine.  infra() calls this, so consumers normally do not."""
    for name in list(_engines):
        await close_database_connection(name)


# ── sessions ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def session_scope(name: str | None = None) -> AsyncIterator[AsyncSession]:
    """A transactional session: rolls back and re-raises on error.  Committing
    remains the caller's job.

    Deliberately NOT a wrapper around ai4i_core.bootstrap.get_db(): that is
    shaped as a FastAPI dependency (an async generator), so an exception in the
    `async with` body propagates out of the `async for` and leaves the generator
    suspended — its rollback branch is then finalised by the event loop's
    async-generator hooks rather than deterministically at the error (§3.3).
    """
    global _default_factory
    if name is None:
        if _default_factory is None:
            # init_database created the engine; get_engine() hands it over, so
            # the default connection is still initialised through ai4i_core.
            _default_factory = async_sessionmaker(
                get_engine(), class_=AsyncSession, expire_on_commit=False
            )
        factory = _default_factory
    else:
        try:
            factory = _session_factories[name]
        except KeyError:
            raise RuntimeError(
                f"database {name!r} was never opened — call add_database({name!r}, ...) first. "
                f"Open: {sorted(_session_factories)}"
            ) from None

    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# ── signals ────────────────────────────────────────────────────────────────
def shutdown_event() -> asyncio.Event:
    """An asyncio.Event set by SIGTERM or SIGINT."""
    loop = asyncio.get_running_loop()
    event = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, event.set)
    return event
