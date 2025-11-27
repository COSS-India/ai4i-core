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
DB_NAME     = str(os.getenv("APP_DB_NAME", "model_management_db"))


AUTH_DB_USER     = os.getenv("AUTH_DB_USER", "auth_user")
AUTH_DB_PASSWORD = os.getenv("AUTH_DB_PASSWORD", "auth_pass")
AUTH_DB_HOST     = os.getenv("AUTH_DB_HOST", "localhost")
AUTH_DB_PORT     = os.getenv("AUTH_DB_PORT", 5433)
AUTH_DB_NAME     = os.getenv("AUTH_DB_NAME", "auth_db")


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
        app_db_connection_string = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

        app_db_engine = create_engine(
            app_db_connection_string,
            pool_pre_ping=True,
            pool_recycle=300,
            echo=False  # Set to True for SQL debugging
        )

        AppDBSessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=app_db_engine
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

        logger.info(f"Connected to PostgreSQL model_management_db: {DB_NAME}@{DB_HOST}:{DB_PORT}")
        logger.info(f"Connected to PostgreSQL auth_db: {AUTH_DB_NAME}@{AUTH_DB_HOST}:{AUTH_DB_PORT}")
    except Exception as e:
        logger.exception(f"Error connecting to PostgreSQL: {e}")
        raise
    

def get_app_db_session():
    """Get a database session for the model management database"""
    if AppDBSessionLocal is None:
        init_postgresql_connections()
    
    db = AppDBSessionLocal()
    try:
        yield db
    finally:
        db.close()

# def get_auth_db_session():
#     """Get a database session for the auth database"""
#     if AuthDBSessionLocal is None:
#         init_postgresql_connections()

#     db = AuthDBSessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()

async def get_auth_db_session():
    if AuthDBSessionLocal is None:
        init_postgresql_connections()

    async with AuthDBSessionLocal() as session:
        yield session

def create_tables():
    """Check existing tables and create missing ones"""
    if app_db_engine is None:
        init_postgresql_connections()

    # check_or_create_schema()

    inspector = inspect(app_db_engine)
    # existing_tables = inspector.get_table_names(schema=DB_SCHEMA)
    existing_tables = inspector.get_table_names()
    all_tables = AppDBBase.metadata.tables.keys()

    missing_tables = [t for t in all_tables if t not in existing_tables]
    if missing_tables:
        logger.info(f"Creating missing tables: {missing_tables}")
        AppDBBase.metadata.create_all(bind=app_db_engine)
    else:
        logger.info("All database tables already exist.")


def AppDatabase() -> Session:
    """Legacy compatibility function - returns model management database session"""
    if AppDBSessionLocal is None:
        init_postgresql_connections()
    return AppDBSessionLocal()

def AuthDatabase() -> Session:
    """Legacy compatibility function - returns auth database session"""
    if AuthDBSessionLocal is None:
        init_postgresql_connections()
    return AuthDBSessionLocal()

# Initialize connections on module import
init_postgresql_connections()
