import os
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from dotenv import load_dotenv

try:
    from ai4icore_logging import get_logger
    logger = get_logger(__name__)
except Exception:
    import logging
    logger = logging.getLogger(__name__)

load_dotenv()

# Database connection settings
DB_USER = str(os.getenv("APP_DB_USER", "dhruva_user"))
DB_PASSWORD = str(os.getenv("APP_DB_PASSWORD", "dhruva_password"))
DB_HOST = str(os.getenv("APP_DB_HOST", "localhost"))
DB_PORT = int(os.getenv("APP_DB_PORT", 5434))
DB_NAME = str(os.getenv("APP_DB_NAME", "model_management_db"))

# PostgreSQL connection engine
app_db_engine: AsyncEngine = None
AppDBSessionLocal: async_sessionmaker = None

# Base class for SQLAlchemy models
AppDBBase = declarative_base()


def init_postgresql_connections():
    """Initialize PostgreSQL database connections"""
    global app_db_engine, AppDBSessionLocal
    
    try:
        # Model management database connection
        app_db_connection_string = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

        app_db_engine = create_async_engine(
            app_db_connection_string,
            pool_size=20,
            max_overflow=10,
            echo=False,
            pool_pre_ping=True,  # Verify connections before using them
            pool_recycle=3600,  # Recycle connections after 1 hour
        )

        AppDBSessionLocal = async_sessionmaker(
            app_db_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

        logger.info(f"Connected to PostgreSQL model_management_db: {DB_NAME}@{DB_HOST}:{DB_PORT}")
    except Exception as e:
        logger.exception(f"Error connecting to PostgreSQL: {e}")
        raise


def AppDatabase() -> AsyncSession:
    """Returns model management database session"""
    if AppDBSessionLocal is None:
        init_postgresql_connections()
    return AppDBSessionLocal()


# Initialize connections on module import
init_postgresql_connections()
