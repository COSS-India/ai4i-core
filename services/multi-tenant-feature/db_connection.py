import os
import asyncio
from sqlalchemy import inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv
from logger import logger

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

load_dotenv()


DB_USER     = str(os.getenv("APP_DB_USER"))
DB_PASSWORD = str(os.getenv("APP_DB_PASSWORD"))
DB_HOST     = str(os.getenv("APP_DB_HOST"))
DB_PORT     = int(os.getenv("APP_DB_PORT"))
DB_NAME     = str(os.getenv("APP_DB_NAME"))


AUTH_DB_USER     = os.getenv("AUTH_DB_USER")
AUTH_DB_PASSWORD = os.getenv("AUTH_DB_PASSWORD")
AUTH_DB_HOST     = os.getenv("AUTH_DB_HOST")
AUTH_DB_PORT     = os.getenv("AUTH_DB_PORT")
AUTH_DB_NAME     = os.getenv("AUTH_DB_NAME")


# PostgreSQL connection engines (set by init_postgresql_connections in lifespan)
tenant_db_engine: AsyncEngine | None = None
auth_db_engine: AsyncEngine | None = None

# Session makers
TenantDBSessionLocal = None
AuthDBSessionLocal = None

# Base classes for SQLAlchemy models
TenantDBBase = declarative_base()
AuthDBBase = declarative_base()
ServiceSchemaBase = declarative_base()


async def wait_for_database(
    engine: AsyncEngine,
    name: str,
    retries: int = 30,
    delay: float = 2.0,
):
    """
    Wait for database to be ready with retry logic.
    Prevents asyncpg CannotConnectNowError when Postgres is still starting (e.g. Docker).
    """
    for attempt in range(1, retries + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info(f"{name} database connection established.")
            return
        except Exception as e:
            logger.warning(f"{name} DB not ready (attempt {attempt}/{retries}): {e}. Retrying in {delay}s...")
            await asyncio.sleep(delay)

    raise Exception(f"{name} database failed to start after {retries} attempts.")


async def init_postgresql_connections():
    """Initialize PostgreSQL database connections with retry. Call from lifespan in main.py."""
    global tenant_db_engine, auth_db_engine
    global TenantDBSessionLocal, AuthDBSessionLocal

    try:
        # Tenant / multi-tenant DB
        tenant_db_connection_string = (
            f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@"
            f"{DB_HOST}:{DB_PORT}/{DB_NAME}"
        )
        tenant_db_engine = create_async_engine(
            tenant_db_connection_string,
            pool_size=20,
            max_overflow=10,
            echo=False,
        )
        await wait_for_database(tenant_db_engine, "Multi-tenant")

        TenantDBSessionLocal = async_sessionmaker(
            tenant_db_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Auth DB
        auth_db_connection_string = (
            f"postgresql+asyncpg://{AUTH_DB_USER}:{AUTH_DB_PASSWORD}@"
            f"{AUTH_DB_HOST}:{AUTH_DB_PORT}/{AUTH_DB_NAME}"
        )
        auth_db_engine = create_async_engine(
            auth_db_connection_string,
            pool_size=20,
            max_overflow=10,
            echo=False,
        )
        await wait_for_database(auth_db_engine, "Auth")

        AuthDBSessionLocal = async_sessionmaker(
            auth_db_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        logger.info(f"Connected to PostgreSQL multi_tenant_db: {DB_NAME}@{DB_HOST}:{DB_PORT}")
        logger.info(f"Connected to PostgreSQL auth_db: {AUTH_DB_NAME}@{AUTH_DB_HOST}:{AUTH_DB_PORT}")

    except Exception as e:
        logger.exception(f"Error connecting to PostgreSQL: {e}")
        raise


async def get_tenant_db_session():
    """Get a database session for the multi-tenant database."""
    if TenantDBSessionLocal is None:
        await init_postgresql_connections()

    async with TenantDBSessionLocal() as session:
        yield session


async def get_auth_db_session():
    """Get a database session for the auth database."""
    if AuthDBSessionLocal is None:
        await init_postgresql_connections()

    async with AuthDBSessionLocal() as session:
        yield session


async def create_tables():
    """Create missing tables. Requires init_postgresql_connections() to have been called (e.g. from lifespan)."""
    if tenant_db_engine is None:
        await init_postgresql_connections()

    # 1. Create tables using async engine
    async with tenant_db_engine.begin() as conn:
        await conn.run_sync(TenantDBBase.metadata.create_all)

    # 2. Get list of existing tables
    def get_existing_tables(sync_conn):
        inspector = inspect(sync_conn)
        return inspector.get_table_names()

    async with tenant_db_engine.connect() as conn:
        existing_tables = await conn.run_sync(get_existing_tables)

    all_tables = list(TenantDBBase.metadata.tables.keys())
    missing = [t for t in all_tables if t not in existing_tables]

    if missing:
        logger.info(f"Created missing tables: {missing}")
    else:
        logger.info("All tables already exist.")


def TenantDatabase() -> AsyncSession:
    """Legacy: returns tenant DB session. Raises if DB not initialized (call init from lifespan first)."""
    if TenantDBSessionLocal is None:
        raise RuntimeError(
            "Database not initialized. Call await init_postgresql_connections() from app lifespan first."
        )
    return TenantDBSessionLocal()


def AuthDatabase() -> AsyncSession:
    """Legacy: returns auth DB session. Raises if DB not initialized."""
    if AuthDBSessionLocal is None:
        raise RuntimeError(
            "Database not initialized. Call await init_postgresql_connections() from app lifespan first."
        )
    return AuthDBSessionLocal()
