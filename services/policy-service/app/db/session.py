from typing import AsyncGenerator

try:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine  # type: ignore
except Exception:  # pragma: no cover
    AsyncEngine = AsyncSession = async_sessionmaker = create_async_engine = None  # type: ignore

from ai4icore_env import app_env  # type: ignore

# Async PostgreSQL connection (aligned with smr-service)
app_db_engine: "AsyncEngine | None" = None
AppDBSessionLocal: "async_sessionmaker[AsyncSession] | None" = None


def init_postgresql_connections() -> None:
    global app_db_engine, AppDBSessionLocal
    if create_async_engine is None:
        raise RuntimeError("SQLAlchemy async engine is unavailable. Check installation.")

    app_db_connection_string = app_env.get_app_database_url()
    app_db_engine = create_async_engine(
        app_db_connection_string,
        pool_size=20,
        max_overflow=10,
        echo=False,
        pool_pre_ping=True,
    )
    AppDBSessionLocal = async_sessionmaker(
        app_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def get_engine() -> "AsyncEngine | None":
    if app_db_engine is None:
        init_postgresql_connections()
    return app_db_engine


async def get_db() -> AsyncGenerator["AsyncSession", None]:
    """
    FastAPI dependency for async DB session.
    """
    if AppDBSessionLocal is None:
        init_postgresql_connections()
    assert AppDBSessionLocal is not None
    async with AppDBSessionLocal() as session:  # type: ignore
        yield session

