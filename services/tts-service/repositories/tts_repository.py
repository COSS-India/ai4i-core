"""
Async repository for TTS database operations.

Adapted from ASR repository for TTS-specific operations.
"""

import logging
from uuid import UUID
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models.database_models import TTSRequestDB, TTSResultDB

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom exception for database operations."""
    pass


class TTSRepository:
    """Async repository for TTS database operations."""
    
    def __init__(self, db: AsyncSession):
        """Initialize repository with async database session."""
        self.db = db
    
    async def create_request(
        self,
        model_id: str,
        voice_id: str,
        language: str,
        text_length: int,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ) -> TTSRequestDB:
        """Create new TTS request record."""
        try:
            request = TTSRequestDB(
                model_id=model_id,
                voice_id=voice_id,
                language=language,
                text_length=text_length,
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id,
                status="processing"
            )
            
            self.db.add(request)
            await self.db.commit()
            await self.db.refresh(request)
            
            logger.info(f"Created TTS request {request.id} for model {model_id}")
            return request
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create TTS request: {e}")
            raise DatabaseError(f"Failed to create TTS request: {e}")
    
    async def update_request_status(
        self,
        request_id: UUID,
        status: str,
        processing_time: Optional[float] = None,
        error_message: Optional[str] = None
    ) -> Optional[TTSRequestDB]:
        """Update TTS request status and metadata."""
        try:
            # Query request by ID
            result = await self.db.execute(
                select(TTSRequestDB).where(TTSRequestDB.id == request_id)
            )
            request = result.scalar_one_or_none()
            
            if not request:
                logger.warning(f"TTS request {request_id} not found")
                return None
            
            # Update fields
            request.status = status
            if processing_time is not None:
                request.processing_time = processing_time
            if error_message is not None:
                request.error_message = error_message
            
            await self.db.commit()
            await self.db.refresh(request)
            
            logger.info(f"Updated TTS request {request_id} status to {status}")
            return request
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update TTS request {request_id}: {e}")
            raise DatabaseError(f"Failed to update TTS request: {e}")
    
    async def create_result(
        self,
        request_id: UUID,
        audio_file_path: str,
        audio_duration: Optional[float] = None,
        audio_format: Optional[str] = None,
        sample_rate: Optional[int] = None,
        bit_rate: Optional[int] = None,
        file_size: Optional[int] = None
    ) -> TTSResultDB:
        """Create new TTS result record."""
        try:
            result = TTSResultDB(
                request_id=request_id,
                audio_file_path=audio_file_path,
                audio_duration=audio_duration,
                audio_format=audio_format,
                sample_rate=sample_rate,
                bit_rate=bit_rate,
                file_size=file_size
            )
            
            self.db.add(result)
            await self.db.commit()
            await self.db.refresh(result)
            
            logger.info(f"Created TTS result {result.id} for request {request_id}")
            return result
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create TTS result for request {request_id}: {e}")
            raise DatabaseError(f"Failed to create TTS result: {e}")
    
    async def get_request_by_id(self, request_id: UUID) -> Optional[TTSRequestDB]:
        """Get TTS request by ID with eager loading of results."""
        try:
            result = await self.db.execute(
                select(TTSRequestDB)
                .options(selectinload(TTSRequestDB.results))
                .where(TTSRequestDB.id == request_id)
            )
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error(f"Failed to get TTS request {request_id}: {e}")
            raise DatabaseError(f"Failed to get TTS request: {e}")
    
    async def get_requests_by_user(
        self,
        user_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> List[TTSRequestDB]:
        """Get TTS requests by user ID with pagination."""
        try:
            result = await self.db.execute(
                select(TTSRequestDB)
                .where(TTSRequestDB.user_id == user_id)
                .order_by(TTSRequestDB.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"Failed to get TTS requests for user {user_id}: {e}")
            raise DatabaseError(f"Failed to get TTS requests: {e}")
    
    async def get_requests_by_status(
        self,
        status: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[TTSRequestDB]:
        """Get TTS requests by status with pagination."""
        try:
            result = await self.db.execute(
                select(TTSRequestDB)
                .where(TTSRequestDB.status == status)
                .order_by(TTSRequestDB.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"Failed to get TTS requests with status {status}: {e}")
            raise DatabaseError(f"Failed to get TTS requests: {e}")


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
