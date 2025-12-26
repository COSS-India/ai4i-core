"""
Database Session Factory

Manages async SQLAlchemy session factory creation and provides dependency injection
for FastAPI routes.
"""

import logging
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from .connection_manager import get_database_engine

logger = logging.getLogger(__name__)

# Global session factory instance
_session_factory: Optional[async_sessionmaker] = None


def create_session_factory(
    engine=None,
    expire_on_commit: bool = False,
    class_: type = AsyncSession,
) -> async_sessionmaker:
    """
    Create an async session factory.
    
    Args:
        engine: AsyncEngine instance. If None, uses the global engine.
        expire_on_commit: Whether to expire instances after commit.
        class_: Session class to use (default: AsyncSession).
    
    Returns:
        Configured async_sessionmaker instance.
    
    Raises:
        RuntimeError: If engine is not provided and global engine is not initialized.
    """
    if engine is None:
        engine = get_database_engine()
    
    if engine is None:
        raise RuntimeError("Database engine not initialized. Call init_database_connections() first.")
    
    factory = async_sessionmaker(
        engine,
        class_=class_,
        expire_on_commit=expire_on_commit,
    )
    
    logger.info("Session factory created successfully")
    return factory


def init_session_factory(
    engine=None,
    expire_on_commit: bool = False,
    class_: type = AsyncSession,
) -> async_sessionmaker:
    """
    Initialize and store the global session factory.
    
    Args:
        engine: AsyncEngine instance. If None, uses the global engine.
        expire_on_commit: Whether to expire instances after commit.
        class_: Session class to use (default: AsyncSession).
    
    Returns:
        The created async_sessionmaker instance.
    """
    global _session_factory
    
    if _session_factory is not None:
        logger.warning("Session factory already initialized, returning existing factory")
        return _session_factory
    
    _session_factory = create_session_factory(
        engine=engine,
        expire_on_commit=expire_on_commit,
        class_=class_,
    )
    
    return _session_factory


def get_session_factory() -> Optional[async_sessionmaker]:
    """
    Get the global session factory instance.
    
    Returns:
        The async_sessionmaker instance, or None if not initialized.
    """
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency function to get a database session.
    
    This function should be used as a dependency in FastAPI routes:
    
    ```python
    @app.get("/items")
    async def get_items(db: AsyncSession = Depends(get_db_session)):
        # Use db session here
        pass
    ```
    
    Yields:
        AsyncSession: Database session instance.
    
    Raises:
        RuntimeError: If session factory is not initialized.
    """
    factory = get_session_factory()
    
    if factory is None:
        raise RuntimeError(
            "Session factory not initialized. "
            "Call init_session_factory() or init_database_connections() first."
        )
    
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()

