from sqlalchemy import create_engine, inspect , text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from ai4icore_env import app_env
from logger import logger

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


# PostgreSQL connection engines
app_db_engine = None
auth_db_engine = None

# Session makers
AppDBSessionLocal = None
AuthDBSessionLocal = None

# Base classes for SQLAlchemy models
AppDBBase = declarative_base()
AuthDBBase = declarative_base()


def init_postgresql_connections():
    """Initialize PostgreSQL database connections"""
    global app_db_engine, auth_db_engine, AppDBSessionLocal , AuthDBSessionLocal
    
    try:
        # Model management database connection
        app_db_connection_string = app_env.get_app_database_url()

        app_db_engine = create_async_engine(
            app_db_connection_string,
            pool_size=20,
            max_overflow=10,
            echo=False
        )

        AppDBSessionLocal = async_sessionmaker(
            app_db_engine,
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

        logger.info(f"Connected to PostgreSQL model_management_db: {app_env.app_db_name}@{app_env.app_db_host}:{app_env.app_db_port}")
        logger.info(f"Connected to PostgreSQL auth_db: {app_env.auth_db_name}@{app_env.auth_db_host}:{app_env.auth_db_port}")
    except Exception as e:
        logger.exception(f"Error connecting to PostgreSQL: {e}")
        raise
    
async def get_app_db_session():
    """Get a database session for the model management database"""
    if AppDBSessionLocal is None:
        init_postgresql_connections()
    
    async with AppDBSessionLocal() as session:
        yield session
   
async def get_auth_db_session():
    if AuthDBSessionLocal is None:
        init_postgresql_connections()

    async with AuthDBSessionLocal() as session:
        yield session

# def create_tables():
#     """Check existing tables and create missing ones"""
#     if app_db_engine is None:
#         init_postgresql_connections()

#     # check_or_create_schema()

#     inspector = inspect(app_db_engine)
#     # existing_tables = inspector.get_table_names(schema=DB_SCHEMA)
#     existing_tables = inspector.get_table_names()
#     all_tables = AppDBBase.metadata.tables.keys()

#     missing_tables = [t for t in all_tables if t not in existing_tables]
#     if missing_tables:
#         logger.info(f"Creating missing tables: {missing_tables}")
#         AppDBBase.metadata.create_all(bind=app_db_engine)
#     else:
#         logger.info("All database tables already exist.")

async def create_tables():
    """Create missing tables for async engine"""

    if app_db_engine is None:
        init_postgresql_connections()

    # 1️⃣ Create tables using async engine
    async with app_db_engine.begin() as conn:
        await conn.run_sync(AppDBBase.metadata.create_all)

    # 2️⃣ Get list of existing tables using a sync inspector
    def get_existing_tables(sync_conn):
        inspector = inspect(sync_conn)
        return inspector.get_table_names()

    async with app_db_engine.connect() as conn:
        existing_tables = await conn.run_sync(get_existing_tables)

    # 3️⃣ Compare with metadata
    all_tables = list(AppDBBase.metadata.tables.keys())
    missing = [t for t in all_tables if t not in existing_tables]

    if missing:
        logger.info(f"Created missing tables: {missing}")
    else:
        logger.info("All tables already exist.")


def AppDatabase() -> AsyncSession:
    """Legacy compatibility function - returns model management database session"""
    if AppDBSessionLocal is None:
        init_postgresql_connections()
    return AppDBSessionLocal()

def AuthDatabase() -> AsyncSession:
    """Legacy compatibility function - returns auth database session"""
    if AuthDBSessionLocal is None:
        init_postgresql_connections()
    return AuthDBSessionLocal()

# Initialize connections on module import
init_postgresql_connections()
