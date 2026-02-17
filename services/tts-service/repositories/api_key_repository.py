"""
API Key repository for authentication database operations.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload
from typing import Optional, List
from datetime import datetime
from models.auth_models import ApiKeyDB
from repositories.tts_repository import DatabaseError
import logging

logger = logging.getLogger(__name__)


class ApiKeyRepository:
    """Repository for API key database operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def find_by_key_hash(self, key_hash: str) -> Optional[ApiKeyDB]:
        """Find API key by key hash with user relationship."""
        try:
            query = select(ApiKeyDB).options(selectinload(ApiKeyDB.user)).where(ApiKeyDB.key_hash == key_hash)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error finding API key by hash: {e}")
            raise DatabaseError(f"Failed to find API key by hash: {e}")
    
    async def find_by_id(self, api_key_id: int) -> Optional[ApiKeyDB]:
        """Find API key by ID."""
        try:
            query = select(ApiKeyDB).where(ApiKeyDB.id == api_key_id)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error finding API key by ID {api_key_id}: {e}")
            raise DatabaseError(f"Failed to find API key by ID: {e}")
    
    async def find_by_user_id(self, user_id: int) -> List[ApiKeyDB]:
        """Find all API keys for a user."""
        try:
            query = select(ApiKeyDB).where(ApiKeyDB.user_id == user_id)
            result = await self.db.execute(query)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error finding API keys for user {user_id}: {e}")
            raise DatabaseError(f"Failed to find API keys for user: {e}")
    
    async def find_active_by_user_id(self, user_id: int) -> List[ApiKeyDB]:
        """Find active API keys for a user."""
        try:
            now = datetime.utcnow()
            query = select(ApiKeyDB).where(
                ApiKeyDB.user_id == user_id,
                ApiKeyDB.is_active == True,
                (ApiKeyDB.expires_at.is_(None)) | (ApiKeyDB.expires_at > now)
            )
            result = await self.db.execute(query)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error finding active API keys for user {user_id}: {e}")
            raise DatabaseError(f"Failed to find active API keys for user: {e}")
    
    async def update_last_used(self, api_key_id: int) -> None:
        """Update last_used_at timestamp for API key."""
        try:
            query = update(ApiKeyDB).where(ApiKeyDB.id == api_key_id).values(last_used_at=func.now())
            await self.db.execute(query)
            await self.db.commit()
        except Exception as e:
            logger.error(f"Error updating last used for API key {api_key_id}: {e}")
            await self.db.rollback()
            raise DatabaseError(f"Failed to update last used: {e}")
    
    async def is_key_valid(self, api_key: ApiKeyDB) -> bool:
        """
        Check if API key is active.

        NOTE:
        - Expiry and permission checks are enforced centrally by auth-service's
          /api/v1/auth/validate-api-key endpoint.
        - To avoid mismatches between this service's local auth schema and the
          central auth database, we only enforce the `is_active` flag here.
        """
        try:
            return bool(api_key.is_active)
        except Exception as e:
            logger.error(f"Error validating API key: {e}")
            return False
