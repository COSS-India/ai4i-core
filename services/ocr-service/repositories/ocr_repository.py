"""
OCR repository utilities.

Currently provides database session dependency hook to align with other
services. Extend with CRUD helpers when OCR results need to be persisted.
"""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom database error for repository operations."""


class OCRRepository:
    """Placeholder repository for OCR persistence (extend as needed)."""

    def __init__(self, db: AsyncSession):
        self.db = db


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function to get a database session from the global factory.
    """
    from main import db_session_factory

    if not db_session_factory:
        raise DatabaseError("Database session factory not initialized")

    async with db_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()

