"""
API Key Repository
Async repository for API key database operations
"""

import logging
from typing import Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from models.auth_models import APIKey

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom database error"""
    pass


class APIKeyRepository:
    """Repository for API key database operations"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def find_by_key_hash(self, key_hash: str) -> Optional[APIKey]:
        """Find API key by hashed key value"""
        try:
            stmt = (
                select(APIKey)
                .options(selectinload(APIKey.user))
                .where(APIKey.key_hash == key_hash)
            )
            
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error(f"Failed to find API key by hash: {e}")
            raise DatabaseError(f"Failed to find API key: {e}")
    
    async def find_by_id(self, api_key_id: int) -> Optional[APIKey]:
        """Find API key by ID"""
        try:
            stmt = (
                select(APIKey)
                .options(selectinload(APIKey.user))
                .where(APIKey.id == api_key_id)
            )
            
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error(f"Failed to find API key by ID {api_key_id}: {e}")
            raise DatabaseError(f"Failed to find API key: {e}")
    
    async def is_key_valid(self, api_key: APIKey) -> bool:
        """Check if API key is active and not expired"""
        try:
            # Check if key is active
            if not api_key.is_active:
                return False
            
            # Check if key has expired
            if api_key.expires_at and api_key.expires_at < datetime.utcnow():
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to validate API key: {e}")
            return False
    
    async def update_last_used(self, api_key_id: int) -> Optional[APIKey]:
        """Update the last_used_at timestamp for an API key"""
        try:
            stmt = (
                update(APIKey)
                .where(APIKey.id == api_key_id)
                .values(last_used_at=datetime.utcnow())
                .returning(APIKey)
            )
            
            result = await self.db.execute(stmt)
            await self.db.commit()
            
            return result.scalar_one_or_none()
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update API key last used timestamp: {e}")
            raise DatabaseError(f"Failed to update API key: {e}")

