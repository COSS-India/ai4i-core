import os
from sqlalchemy import create_engine, inspect , text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv
from logger import logger

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

load_dotenv()



DB_USER     = str(os.getenv("APP_DB_USER", "dhruva_user"))
DB_PASSWORD = str(os.getenv("APP_DB_PASSWORD", "dhruva_password"))
DB_HOST     = str(os.getenv("APP_DB_HOST", "localhost"))
DB_PORT     = int(os.getenv("APP_DB_PORT",5434))
DB_NAME     = str(os.getenv("APP_DB_NAME", "multi_tenant_db"))


AUTH_DB_USER     = os.getenv("AUTH_DB_USER", "auth_user")
AUTH_DB_PASSWORD = os.getenv("AUTH_DB_PASSWORD", "auth_pass")
AUTH_DB_HOST     = os.getenv("AUTH_DB_HOST", "localhost")
AUTH_DB_PORT     = os.getenv("AUTH_DB_PORT", 5433)
AUTH_DB_NAME     = os.getenv("AUTH_DB_NAME", "auth_db")


# PostgreSQL connection engines
tenant_db_engine = None
auth_db_engine = None

# Session makers
TenantDBSessionLocal = None
AuthDBSessionLocal = None

# Base classes for SQLAlchemy models
TenantDBBase = declarative_base()  # For tenant management tables (Tenant, BillingRecord, etc.) in public schema
AuthDBBase = declarative_base()    # For auth tables (users, api_keys, etc.) in auth_db
ServiceSchemaBase = declarative_base()  # For service tables (NMT, TTS, ASR, etc.) in tenant schemas


def init_postgresql_connections():
    """Initialize PostgreSQL database connections"""
    global tenant_db_engine, auth_db_engine, TenantDBSessionLocal , AuthDBSessionLocal
    
    try:
        # Model management database connection
        tenant_db_connection_string = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

        tenant_db_engine = create_async_engine(
            tenant_db_connection_string,
            pool_size=20,
            max_overflow=10,
            echo=False
        )

        TenantDBSessionLocal = async_sessionmaker(
            tenant_db_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

        auth_db_connection_string = f"postgresql+asyncpg://{AUTH_DB_USER}:{AUTH_DB_PASSWORD}@{AUTH_DB_HOST}:{AUTH_DB_PORT}/{AUTH_DB_NAME}"
    
        auth_db_engine = create_async_engine(
            auth_db_connection_string,
            pool_size=20,
            max_overflow=10,
            echo=False
        )
    
        AuthDBSessionLocal = async_sessionmaker(
            auth_db_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

        logger.info(f"Connected to PostgreSQL multi_tenant_db: {DB_NAME}@{DB_HOST}:{DB_PORT}")
        logger.info(f"Connected to PostgreSQL auth_db: {AUTH_DB_NAME}@{AUTH_DB_HOST}:{AUTH_DB_PORT}")
    except Exception as e:
        logger.exception(f"Error connecting to PostgreSQL: {e}")
        raise
    
async def get_tenant_db_session():
    """Get a database session for the multi-tenant database"""
    if TenantDBSessionLocal is None:
        init_postgresql_connections()
    
    async with TenantDBSessionLocal() as session:
        yield session
   
async def get_auth_db_session():
    if AuthDBSessionLocal is None:
        init_postgresql_connections()

    async with AuthDBSessionLocal() as session:
        yield session

async def create_tables():
    """Create missing tables for async engine"""

    if tenant_db_engine is None:
        init_postgresql_connections()

    # 1️⃣ Create tables using async engine
    async with tenant_db_engine.begin() as conn:
        await conn.run_sync(TenantDBBase.metadata.create_all)

    # 2️⃣ Get list of existing tables using a sync inspector
    def get_existing_tables(sync_conn):
        inspector = inspect(sync_conn)
        return inspector.get_table_names()

    async with tenant_db_engine.connect() as conn:
        existing_tables = await conn.run_sync(get_existing_tables)

    # 3️⃣ Compare with metadata
    all_tables = list(TenantDBBase.metadata.tables.keys())
    missing = [t for t in all_tables if t not in existing_tables]

    if missing:
        logger.info(f"Created missing tables: {missing}")
    else:
        logger.info("All tables already exist.")


def TenantDatabase() -> AsyncSession:
    """Legacy compatibility function - returns muti-tenant database session"""
    if TenantDBSessionLocal is None:
        init_postgresql_connections()
    return TenantDBSessionLocal()

def AuthDatabase() -> AsyncSession:
    """Legacy compatibility function - returns auth database session"""
    if AuthDBSessionLocal is None:
        init_postgresql_connections()
    return AuthDBSessionLocal()

# Initialize connections on module import
init_postgresql_connections()