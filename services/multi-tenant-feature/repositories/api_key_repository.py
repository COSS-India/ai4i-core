"""
API Key Repository
Async repository for API key database operations
"""

import logging
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from models.auth_models import ApiKeyDB

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom database error"""
    pass


class ApiKeyRepository:
    """Repository for API key database operations"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def find_by_key_hash(self, key_hash: str) -> Optional[ApiKeyDB]:
        """Find API key by hashed key value"""
        try:
            stmt = (
                select(ApiKeyDB)
                .options(selectinload(ApiKeyDB.user))
                .where(ApiKeyDB.key_hash == key_hash)
            )
            
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error(f"Failed to find API key by hash: {e}")
            raise DatabaseError(f"Failed to find API key: {e}")
    
    async def find_by_id(self, api_key_id: int) -> Optional[ApiKeyDB]:
        """Find API key by ID"""
        try:
            stmt = (
                select(ApiKeyDB)
                .options(selectinload(ApiKeyDB.user))
                .where(ApiKeyDB.id == api_key_id)
            )
            
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error(f"Failed to find API key by ID {api_key_id}: {e}")
            raise DatabaseError(f"Failed to find API key: {e}")
    
    async def is_key_valid(self, api_key: ApiKeyDB) -> bool:
        """Check if API key is active and not expired"""
        try:
            # Check if key is active
            if not api_key.is_active:
                return False
            
            # Check if key has expired (use timezone-aware datetime)
            if api_key.expires_at:
                # Ensure we're comparing timezone-aware datetimes
                now = datetime.now(timezone.utc)
                if api_key.expires_at < now:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to validate API key: {e}")
            return False
    
    async def update_last_used(self, api_key_id: int) -> Optional[ApiKeyDB]:
        """Update the last_used timestamp for an API key"""
        try:
            stmt = (
                update(ApiKeyDB)
                .where(ApiKeyDB.id == api_key_id)
                .values(last_used=datetime.now(timezone.utc))
                .returning(ApiKeyDB)
            )
            
            result = await self.db.execute(stmt)
            await self.db.commit()
            
            return result.scalar_one_or_none()
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update API key last used timestamp: {e}")
            raise DatabaseError(f"Failed to update API key: {e}")