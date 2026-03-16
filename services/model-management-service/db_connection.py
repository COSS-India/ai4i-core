import asyncio
from sqlalchemy import create_engine, inspect , text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from ai4icore_env import app_env
from logger import logger

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

# Engines
app_db_engine: AsyncEngine | None = None
auth_db_engine: AsyncEngine | None = None
# Engines
app_db_engine: AsyncEngine | None = None
auth_db_engine: AsyncEngine | None = None

# Session makers
AppDBSessionLocal = None
AuthDBSessionLocal = None

# Base classes
AppDBBase = declarative_base()
AuthDBBase = declarative_base()


async def wait_for_database(engine: AsyncEngine, name: str, retries: int = 10, delay: int = 2):
    """
    Wait for database to be ready with retry logic.
    This prevents asyncpg startup race condition.
    """
    for attempt in range(1, retries + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info(f"{name} database connection established.")
            return
        except Exception as e:
            logger.warning(
                f"{name} DB not ready (attempt {attempt}/{retries}). Retrying in {delay}s..."
            )
            await asyncio.sleep(delay)

    raise Exception(f"{name} database failed to start after {retries} attempts.")


async def init_postgresql_connections():
    """Initialize PostgreSQL database connections with retry"""

    global app_db_engine, auth_db_engine
    global AppDBSessionLocal, AuthDBSessionLocal

    try:
        # Model management database connection
        app_db_connection_string = app_env.get_app_database_url()

        app_db_engine = create_async_engine(
            app_db_connection_string,
            pool_size=20,
            max_overflow=10,
            echo=False,
        )

        await wait_for_database(app_db_engine, "Model Management")

        AppDBSessionLocal = async_sessionmaker(
            app_db_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        auth_db_connection_string = app_env.get_auth_database_url()
    
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

        logger.info(f"Connected to PostgreSQL model_management_db: {app_env.app_db_name}@{app_env.app_db_host}:{app_env.app_db_port}")
        logger.info(f"Connected to PostgreSQL auth_db: {app_env.auth_db_name}@{app_env.auth_db_host}:{app_env.auth_db_port}")
    except Exception as e:
        logger.exception(f"Error connecting to PostgreSQL: {e}")
        raise


async def get_app_db_session():
    if AppDBSessionLocal is None:
        await init_postgresql_connections()

    async with AppDBSessionLocal() as session:
        yield session


async def get_auth_db_session():
    if AuthDBSessionLocal is None:
        await init_postgresql_connections()

    async with AuthDBSessionLocal() as session:
        yield session


async def create_tables():
    """Create missing tables safely with async engine"""

    if app_db_engine is None:
        await init_postgresql_connections()

    async with app_db_engine.begin() as conn:
        await conn.run_sync(AppDBBase.metadata.create_all)

    def get_existing_tables(sync_conn):
        inspector = inspect(sync_conn)
        return inspector.get_table_names()

    async with app_db_engine.connect() as conn:
        existing_tables = await conn.run_sync(get_existing_tables)

    all_tables = list(AppDBBase.metadata.tables.keys())
    missing = [t for t in all_tables if t not in existing_tables]

    if missing:
        logger.info(f"Created missing tables: {missing}")
    else:
        logger.info("All tables already exist.")


def AppDatabase() -> AsyncSession:
    if AppDBSessionLocal is None:
        raise Exception("Database not initialized. Call init_postgresql_connections() first.")
    return AppDBSessionLocal()


def AuthDatabase() -> AsyncSession:
    if AuthDBSessionLocal is None:
        raise Exception("Database not initialized. Call init_postgresql_connections() first.")
    return AuthDBSessionLocal()