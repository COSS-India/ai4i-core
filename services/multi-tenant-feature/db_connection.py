from sqlalchemy import create_engine, inspect , text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from ai4icore_env import app_env
from logger import logger

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


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
        tenant_db_connection_string = app_env.get_app_database_url()

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

        auth_db_connection_string = app_env.get_auth_database_url()
    
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

        logger.info(f"Connected to PostgreSQL multi_tenant_db: {app_env.app_db_name}@{app_env.app_db_host}:{app_env.app_db_port}")
        logger.info(f"Connected to PostgreSQL auth_db: {app_env.auth_db_name}@{app_env.auth_db_host}:{app_env.auth_db_port}")
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