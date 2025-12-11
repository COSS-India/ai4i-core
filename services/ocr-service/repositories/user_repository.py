"""
User repository for OCR service.

Matches the structure used in NMT/ASR so auth lookups behave consistently.
"""

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models.auth_models import UserDB

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom database error."""


class UserRepository:
    """Repository for user database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_by_id(self, user_id: int) -> Optional[UserDB]:
        """Find user by ID."""
        try:
            stmt = (
                select(UserDB)
                .options(selectinload(UserDB.api_keys))
                .where(UserDB.id == user_id)
            )

            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()

        except Exception as exc:
            logger.error("Failed to find user by ID %s: %s", user_id, exc)
            raise DatabaseError(f"Failed to find user: {exc}")

    async def find_by_email(self, email: str) -> Optional[UserDB]:
        """Find user by email address."""
        try:
            stmt = (
                select(UserDB)
                .options(selectinload(UserDB.api_keys))
                .where(UserDB.email == email)
            )

            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()

        except Exception as exc:
            logger.error("Failed to find user by email %s: %s", email, exc)
            raise DatabaseError(f"Failed to find user: {exc}")

