"""
User repository for authentication database operations.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List
from models.auth_models import UserDB
from repositories.tts_repository import DatabaseError
import logging

logger = logging.getLogger(__name__)


class UserRepository:
    """Repository for user database operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def find_by_id(self, user_id: int) -> Optional[UserDB]:
        """Find user by ID."""
        try:
            query = select(UserDB).where(UserDB.id == user_id)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error finding user by ID {user_id}: {e}")
            raise DatabaseError(f"Failed to find user by ID: {e}")
    
    async def find_by_email(self, email: str) -> Optional[UserDB]:
        """Find user by email."""
        try:
            query = select(UserDB).where(UserDB.email == email)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error finding user by email {email}: {e}")
            raise DatabaseError(f"Failed to find user by email: {e}")
    
    async def find_by_username(self, username: str) -> Optional[UserDB]:
        """Find user by username."""
        try:
            query = select(UserDB).where(UserDB.username == username)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error finding user by username {username}: {e}")
            raise DatabaseError(f"Failed to find user by username: {e}")
    
    async def find_active_users(self, limit: int = 100, offset: int = 0) -> List[UserDB]:
        """Find active users with pagination."""
        try:
            query = select(UserDB).where(UserDB.is_active == True).offset(offset).limit(limit)
            result = await self.db.execute(query)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error finding active users: {e}")
            raise DatabaseError(f"Failed to find active users: {e}")
    
    async def update_last_login(self, user_id: int) -> None:
        """Update user's last login timestamp."""
        try:
            # Note: This assumes there's a last_login_at field in the UserDB model
            # If not present, this method can be removed or modified
            query = select(UserDB).where(UserDB.id == user_id)
            result = await self.db.execute(query)
            user = result.scalar_one_or_none()
            
            if user:
                # Update last_login_at if the field exists
                # For now, we'll update the updated_at field as a proxy
                from sqlalchemy import update, func
                update_query = update(UserDB).where(UserDB.id == user_id).values(updated_at=func.now())
                await self.db.execute(update_query)
                await self.db.commit()
        except Exception as e:
            logger.error(f"Error updating last login for user {user_id}: {e}")
            await self.db.rollback()
            raise DatabaseError(f"Failed to update last login: {e}")
