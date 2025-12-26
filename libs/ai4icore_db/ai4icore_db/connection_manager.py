"""
Database Connection Manager

Manages async PostgreSQL database connections using SQLAlchemy.
"""

import os
import logging
from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine

logger = logging.getLogger(__name__)

# Global engine instance
_db_engine: Optional[AsyncEngine] = None


def create_database_engine(
    database_url: Optional[str] = None,
    pool_size: int = 20,
    max_overflow: int = 10,
    pool_pre_ping: bool = True,
    pool_recycle: int = 3600,
    echo: bool = False,
    connect_args: Optional[dict] = None,
) -> AsyncEngine:
    """
    Create and configure an async database engine.
    
    Args:
        database_url: PostgreSQL connection string. If None, reads from DATABASE_URL env var.
        pool_size: Number of connections to maintain in the pool.
        max_overflow: Maximum number of connections to allow beyond pool_size.
        pool_pre_ping: Enable connection health checks on checkout.
        pool_recycle: Seconds after which to recycle connections.
        echo: Enable SQL query logging.
        connect_args: Additional connection arguments.
    
    Returns:
        Configured AsyncEngine instance.
    """
    if database_url is None:
        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@postgres:5432/auth_db"
        )
    
    if connect_args is None:
        connect_args = {"timeout": 30, "command_timeout": 30}
    
    engine = create_async_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=pool_pre_ping,
        pool_recycle=pool_recycle,
        echo=echo,
        connect_args=connect_args,
    )
    
    logger.info(f"Database engine created with pool_size={pool_size}, max_overflow={max_overflow}")
    return engine


def init_database_connections(
    database_url: Optional[str] = None,
    pool_size: Optional[int] = None,
    max_overflow: Optional[int] = None,
    pool_pre_ping: bool = True,
    pool_recycle: int = 3600,
    echo: bool = False,
    test_connection: bool = True,
) -> AsyncEngine:
    """
    Initialize database connections and store globally.
    
    Args:
        database_url: PostgreSQL connection string. If None, reads from DATABASE_URL env var.
        pool_size: Number of connections to maintain. If None, reads from DB_POOL_SIZE env var.
        max_overflow: Maximum overflow connections. If None, reads from DB_MAX_OVERFLOW env var.
        pool_pre_ping: Enable connection health checks.
        pool_recycle: Seconds after which to recycle connections.
        echo: Enable SQL query logging.
        test_connection: Whether to test the connection after creation.
    
    Returns:
        The created AsyncEngine instance.
    """
    global _db_engine
    
    if _db_engine is not None:
        logger.warning("Database engine already initialized, returning existing engine")
        return _db_engine
    
    # Read configuration from environment if not provided
    if pool_size is None:
        pool_size = int(os.getenv("DB_POOL_SIZE", "20"))
    
    if max_overflow is None:
        max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    
    # Create engine
    _db_engine = create_database_engine(
        database_url=database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=pool_pre_ping,
        pool_recycle=pool_recycle,
        echo=echo,
    )
    
    # Test connection if requested
    if test_connection:
        test_database_connection(_db_engine)
    
    logger.info("Database connections initialized successfully")
    return _db_engine


async def close_database_connections() -> None:
    """
    Close all database connections and dispose of the engine.
    """
    global _db_engine
    
    if _db_engine is not None:
        logger.info("Closing database connections...")
        await _db_engine.dispose()
        _db_engine = None
        logger.info("Database connections closed")
    else:
        logger.debug("No database engine to close")


def get_database_engine() -> Optional[AsyncEngine]:
    """
    Get the global database engine instance.
    
    Returns:
        The AsyncEngine instance, or None if not initialized.
    """
    return _db_engine


async def test_database_connection(engine: Optional[AsyncEngine] = None) -> bool:
    """
    Test database connection by executing a simple query.
    
    Args:
        engine: Engine to test. If None, uses the global engine.
    
    Returns:
        True if connection is successful, False otherwise.
    
    Raises:
        RuntimeError: If engine is not provided and not initialized.
    """
    if engine is None:
        engine = _db_engine
    
    if engine is None:
        raise RuntimeError("Database engine not initialized")
    
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection test successful")
        return True
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        raise

