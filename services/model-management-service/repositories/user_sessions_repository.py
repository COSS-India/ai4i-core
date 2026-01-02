from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from sqlalchemy.orm import selectinload
from typing import Optional, List
from datetime import datetime
from models.auth_models import UserSession
from logger import logger

class DatabaseError(Exception):
    """Custom database error"""
    pass


class UserSessionRepository:
    """Repository for session database operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def find_by_user_id(self, user_id: int) -> List[UserSession]:
        """Find all sessions for a user."""
        try:
            query = select(UserSession).where(UserSession.user_id == user_id).order_by(UserSession.created_at.desc())
            result = await self.db.execute(query)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error finding sessions for user {user_id}: {e}")
            raise DatabaseError(f"Failed to find sessions for user: {e}")
    