"""
Session repository for authentication database operations.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from sqlalchemy.orm import selectinload
from typing import Optional, List
from datetime import datetime
from models.auth_models import Session
from repositories.language_detection_repository import DatabaseError
import logging

logger = logging.getLogger(__name__)


class SessionRepository:
    """Repository for session database operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def find_by_token(self, session_token: str) -> Optional[Session]:
        """Find session by token with user relationship."""
        try:
            query = select(Session).options(selectinload(Session.user)).where(Session.session_token == session_token)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error finding session by token: {e}")
            raise DatabaseError(f"Failed to find session by token: {e}")
    
    async def find_by_id(self, session_id: int) -> Optional[Session]:
        """Find session by ID."""
        try:
            query = select(Session).where(Session.id == session_id)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error finding session by ID {session_id}: {e}")
            raise DatabaseError(f"Failed to find session by ID: {e}")
    
    async def find_by_user_id(self, user_id: int) -> List[Session]:
        """Find all sessions for a user."""
        try:
            query = select(Session).where(Session.user_id == user_id).order_by(Session.created_at.desc())
            result = await self.db.execute(query)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error finding sessions for user {user_id}: {e}")
            raise DatabaseError(f"Failed to find sessions for user: {e}")
    
    async def create_session(self, user_id: int, session_token: str, ip_address: Optional[str] = None, 
                           user_agent: Optional[str] = None, expires_at: datetime = None) -> Session:
        """Create new session record."""
        try:
            if expires_at is None:
                expires_at = datetime.utcnow().replace(hour=23, minute=59, second=59)  # End of day
            
            session = Session(
                user_id=user_id,
                session_token=session_token,
                ip_address=ip_address,
                user_agent=user_agent,
                expires_at=expires_at
            )
            
            self.db.add(session)
            await self.db.commit()
            await self.db.refresh(session)
            return session
        except Exception as e:
            logger.error(f"Error creating session for user {user_id}: {e}")
            await self.db.rollback()
            raise DatabaseError(f"Failed to create session: {e}")
    
    async def delete_session(self, session_id: int) -> bool:
        """Delete session by ID."""
        try:
            query = delete(Session).where(Session.id == session_id)
            result = await self.db.execute(query)
            await self.db.commit()
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting session {session_id}: {e}")
            await self.db.rollback()
            raise DatabaseError(f"Failed to delete session: {e}")
    
    async def is_session_valid(self, session: Session) -> bool:
        """Check if session is not expired."""
        try:
            return session.expires_at > datetime.utcnow()
        except Exception as e:
            logger.error(f"Error validating session: {e}")
            return False
    
    async def cleanup_expired_sessions(self) -> int:
        """Delete all expired sessions."""
        try:
            query = delete(Session).where(Session.expires_at < func.now())
            result = await self.db.execute(query)
            await self.db.commit()
            return result.rowcount
        except Exception as e:
            logger.error(f"Error cleaning up expired sessions: {e}")
            await self.db.rollback()
            raise DatabaseError(f"Failed to cleanup expired sessions: {e}")

