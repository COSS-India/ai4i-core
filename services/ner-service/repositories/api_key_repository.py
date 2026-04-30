"""
API Key repository for NER service.

Copied from OCR service to keep auth behavior consistent.
"""

import logging
from typing import Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from models.auth_models import ApiKeyDB

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom database error."""


class ApiKeyRepository:
    """Repository for API key database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_by_key_hash(self, key_hash: str) -> Optional[ApiKeyDB]:
        """Find API key by hashed key value."""
        try:
            stmt = (
                select(ApiKeyDB)
                .options(selectinload(ApiKeyDB.user))
                .where(ApiKeyDB.key_hash == key_hash)
            )

            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()

        except Exception as exc:
            logger.error("Failed to find API key by hash: %s", exc)
            raise DatabaseError(f"Failed to find API key: {exc}")

    async def find_by_id(self, api_key_id: int) -> Optional[ApiKeyDB]:
        """Find API key by ID."""
        try:
            stmt = (
                select(ApiKeyDB)
                .options(selectinload(ApiKeyDB.user))
                .where(ApiKeyDB.id == api_key_id)
            )

            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()

        except Exception as exc:
            logger.error("Failed to find API key by ID %s: %s", api_key_id, exc)
            raise DatabaseError(f"Failed to find API key: {exc}")

    async def is_key_valid(self, api_key: ApiKeyDB) -> bool:
        """Check if API key is active and not expired."""
        try:
            if not api_key.is_active:
                return False

            if api_key.expires_at and api_key.expires_at < datetime.utcnow():
                return False

            return True

        except Exception as exc:
            logger.error("Failed to validate API key: %s", exc)
            return False

    async def update_last_used(self, api_key_id: int) -> Optional[ApiKeyDB]:
        """Update the last_used_at timestamp for an API key."""
        try:
            stmt = (
                update(ApiKeyDB)
                .where(ApiKeyDB.id == api_key_id)
                .values(last_used_at=datetime.utcnow())
                .returning(ApiKeyDB)
            )

            result = await self.db.execute(stmt)
            await self.db.commit()

            return result.scalar_one_or_none()

        except Exception as exc:
            await self.db.rollback()
            logger.error("Failed to update API key last used timestamp: %s", exc)
            raise DatabaseError(f"Failed to update API key: {exc}")
