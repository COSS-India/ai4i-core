"""
Transliteration Repository
Async repository for transliteration database operations
"""

import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from models.database_models import TransliterationRequestDB, TransliterationResultDB

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom database error"""
    pass


class TransliterationRepository:
    """Repository for transliteration database operations"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_request(
        self,
        model_id: str,
        source_language: str,
        target_language: str,
        text_length: int,
        is_sentence_level: bool = True,
        num_suggestions: int = 0,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ) -> TransliterationRequestDB:
        """Create new transliteration request record"""
        try:
            request = TransliterationRequestDB(
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id,
                model_id=model_id,
                source_language=source_language,
                target_language=target_language,
                text_length=text_length,
                is_sentence_level=is_sentence_level,
                num_suggestions=num_suggestions,
                status="processing"
            )
            
            self.db.add(request)
            await self.db.commit()
            await self.db.refresh(request)
            
            logger.info(f"Created transliteration request {request.id}")
            return request
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create transliteration request: {e}")
            raise DatabaseError(f"Failed to create transliteration request: {e}")
    
    async def update_request_status(
        self,
        request_id: UUID,
        status: str,
        processing_time: Optional[float] = None,
        error_message: Optional[str] = None
    ) -> TransliterationRequestDB:
        """Update transliteration request status"""
        try:
            stmt = (
                update(TransliterationRequestDB)
                .where(TransliterationRequestDB.id == request_id)
                .values(
                    status=status,
                    processing_time=processing_time,
                    error_message=error_message
                )
                .returning(TransliterationRequestDB)
            )
            
            result = await self.db.execute(stmt)
            await self.db.commit()
            
            request = result.scalar_one_or_none()
            if not request:
                raise DatabaseError(f"Transliteration request {request_id} not found")
            
            logger.info(f"Updated transliteration request {request_id} status to {status}")
            return request
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update transliteration request {request_id}: {e}")
            raise DatabaseError(f"Failed to update transliteration request: {e}")
    
    async def create_result(
        self,
        request_id: UUID,
        transliterated_text: any,  # Can be string or list
        source_text: str,
        confidence_score: Optional[float] = None
    ) -> TransliterationResultDB:
        """Create new transliteration result record"""
        try:
            result = TransliterationResultDB(
                request_id=request_id,
                transliterated_text=transliterated_text,
                source_text=source_text,
                confidence_score=confidence_score
            )
            
            self.db.add(result)
            await self.db.commit()
            await self.db.refresh(result)
            
            logger.info(f"Created transliteration result {result.id} for request {request_id}")
            return result
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create transliteration result: {e}")
            raise DatabaseError(f"Failed to create transliteration result: {e}")
    
    async def get_request_by_id(self, request_id: UUID) -> Optional[TransliterationRequestDB]:
        """Get transliteration request by ID with results"""
        try:
            stmt = (
                select(TransliterationRequestDB)
                .options(selectinload(TransliterationRequestDB.results))
                .where(TransliterationRequestDB.id == request_id)
            )
            
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error(f"Failed to get transliteration request {request_id}: {e}")
            raise DatabaseError(f"Failed to get transliteration request: {e}")
    
    async def get_requests_by_user(
        self,
        user_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> List[TransliterationRequestDB]:
        """Get transliteration requests by user with pagination"""
        try:
            stmt = (
                select(TransliterationRequestDB)
                .where(TransliterationRequestDB.user_id == user_id)
                .order_by(TransliterationRequestDB.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            
            result = await self.db.execute(stmt)
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"Failed to get transliteration requests for user {user_id}: {e}")
            raise DatabaseError(f"Failed to get transliteration requests: {e}")


async def get_db_session() -> AsyncSession:
    """Dependency function to get database session."""
    # This will be injected by FastAPI dependency injection
    # The actual session will be provided by the main app
    from main import db_session_factory
    
    if not db_session_factory:
        raise DatabaseError("Database session factory not initialized")
    
    async with db_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()

