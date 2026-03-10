# import os
# from sqlalchemy import create_engine, inspect , text
# from sqlalchemy.ext.declarative import declarative_base
# from sqlalchemy.orm import sessionmaker, Session
# from dotenv import load_dotenv
# from logger import logger

# from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

# load_dotenv()



# DB_USER     = str(os.getenv("APP_DB_USER", "dhruva_user"))
# DB_PASSWORD = str(os.getenv("APP_DB_PASSWORD", "dhruva_password"))
# DB_HOST     = str(os.getenv("APP_DB_HOST", "localhost"))
# DB_PORT     = int(os.getenv("APP_DB_PORT",5434))
# DB_NAME     = str(os.getenv("APP_DB_NAME", "model_management_db"))

# AUTH_DB_USER     = os.getenv("AUTH_DB_USER", "auth_user")
# AUTH_DB_PASSWORD = os.getenv("AUTH_DB_PASSWORD", "auth_pass")
# AUTH_DB_HOST     = os.getenv("AUTH_DB_HOST", "localhost")
# AUTH_DB_PORT     = os.getenv("AUTH_DB_PORT", 5433)
# AUTH_DB_NAME     = os.getenv("AUTH_DB_NAME", "auth_db")


# # PostgreSQL connection engines
# app_db_engine = None
# auth_db_engine = None

# # Session makers
# AppDBSessionLocal = None
# AuthDBSessionLocal = None

# # Base classes for SQLAlchemy models
# AppDBBase = declarative_base()
# AuthDBBase = declarative_base()


# def init_postgresql_connections():
#     """Initialize PostgreSQL database connections"""
#     global app_db_engine, auth_db_engine, AppDBSessionLocal , AuthDBSessionLocal
    
#     try:
#         # Model management database connection
#         app_db_connection_string = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

#         app_db_engine = create_async_engine(
#             app_db_connection_string,
#             pool_size=20,
#             max_overflow=10,
#             echo=False
#         )

#         AppDBSessionLocal = async_sessionmaker(
#             app_db_engine,
#             class_=AsyncSession,
#             expire_on_commit=False
#         )

#         auth_db_connection_string = f"postgresql+asyncpg://{AUTH_DB_USER}:{AUTH_DB_PASSWORD}@{AUTH_DB_HOST}:{AUTH_DB_PORT}/{AUTH_DB_NAME}"
    
#         auth_db_engine = create_async_engine(
#             auth_db_connection_string,
#             pool_size=20,
#             max_overflow=10,
#             echo=False
#         )
    
#         AuthDBSessionLocal = async_sessionmaker(
#             auth_db_engine,
#             class_=AsyncSession,
#             expire_on_commit=False
#         )

#         logger.info(f"Connected to PostgreSQL model_management_db: {DB_NAME}@{DB_HOST}:{DB_PORT}")
#         logger.info(f"Connected to PostgreSQL auth_db: {AUTH_DB_NAME}@{AUTH_DB_HOST}:{AUTH_DB_PORT}")
#     except Exception as e:
#         logger.exception(f"Error connecting to PostgreSQL: {e}")
#         raise
    
# async def get_app_db_session():
#     """Get a database session for the model management database"""
#     if AppDBSessionLocal is None:
#         init_postgresql_connections()
    
#     async with AppDBSessionLocal() as session:
#         yield session
   
# async def get_auth_db_session():
#     if AuthDBSessionLocal is None:
#         init_postgresql_connections()

#     async with AuthDBSessionLocal() as session:
#         yield session

# # def create_tables():
# #     """Check existing tables and create missing ones"""
# #     if app_db_engine is None:
# #         init_postgresql_connections()

# #     # check_or_create_schema()

# #     inspector = inspect(app_db_engine)
# #     # existing_tables = inspector.get_table_names(schema=DB_SCHEMA)
# #     existing_tables = inspector.get_table_names()
# #     all_tables = AppDBBase.metadata.tables.keys()

# #     missing_tables = [t for t in all_tables if t not in existing_tables]
# #     if missing_tables:
# #         logger.info(f"Creating missing tables: {missing_tables}")
# #         AppDBBase.metadata.create_all(bind=app_db_engine)
# #     else:
# #         logger.info("All database tables already exist.")

# async def create_tables():
#     """Create missing tables for async engine"""

#     if app_db_engine is None:
#         init_postgresql_connections()

#     # 1️⃣ Create tables using async engine
#     async with app_db_engine.begin() as conn:
#         await conn.run_sync(AppDBBase.metadata.create_all)

#     # 2️⃣ Get list of existing tables using a sync inspector
#     def get_existing_tables(sync_conn):
#         inspector = inspect(sync_conn)
#         return inspector.get_table_names()

#     async with app_db_engine.connect() as conn:
#         existing_tables = await conn.run_sync(get_existing_tables)

#     # 3️⃣ Compare with metadata
#     all_tables = list(AppDBBase.metadata.tables.keys())
#     missing = [t for t in all_tables if t not in existing_tables]

#     if missing:
#         logger.info(f"Created missing tables: {missing}")
#     else:
#         logger.info("All tables already exist.")


# def AppDatabase() -> AsyncSession:
#     """Legacy compatibility function - returns model management database session"""
#     if AppDBSessionLocal is None:
#         init_postgresql_connections()
#     return AppDBSessionLocal()

# def AuthDatabase() -> AsyncSession:
#     """Legacy compatibility function - returns auth database session"""
#     if AuthDBSessionLocal is None:
#         init_postgresql_connections()
#     return AuthDBSessionLocal()

# # # Initialize connections on module import
# # init_postgresql_connections()

import os
import asyncio
from sqlalchemy import inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine
)
from dotenv import load_dotenv
from logger import logger

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
        # Model Management DB
        app_conn_str = (
            f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@"
            f"{DB_HOST}:{DB_PORT}/{DB_NAME}"
        )

        app_db_engine = create_async_engine(
            app_conn_str,
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

        # Auth DB
        auth_conn_str = (
            f"postgresql+asyncpg://{AUTH_DB_USER}:{AUTH_DB_PASSWORD}@"
            f"{AUTH_DB_HOST}:{AUTH_DB_PORT}/{AUTH_DB_NAME}"
        )

        auth_db_engine = create_async_engine(
            auth_conn_str,
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

        logger.info("PostgreSQL connections initialized successfully.")

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