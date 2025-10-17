"""
Async repository for ASR database operations.

Adapted from Dhruva-Platform-2 PostgreSQLBaseRepository for async SQLAlchemy.
"""

import logging
from uuid import UUID
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from models.database_models import ASRRequestDB, ASRResultDB

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom exception for database operations."""
    pass


class ASRRepository:
    """Async repository for ASR database operations."""
    
    def __init__(self, db: AsyncSession):
        """Initialize repository with async database session."""
        self.db = db
    
    async def create_request(
        self,
        model_id: str,
        language: str,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ) -> ASRRequestDB:
        """Create new ASR request record."""
        try:
            request = ASRRequestDB(
                model_id=model_id,
                language=language,
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id,
                status="processing"
            )
            
            self.db.add(request)
            await self.db.commit()
            await self.db.refresh(request)
            
            logger.info(f"Created ASR request {request.id} for model {model_id}")
            return request
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create ASR request: {e}")
            raise DatabaseError(f"Failed to create ASR request: {e}")
    
    async def update_request_status(
        self,
        request_id: UUID,
        status: str,
        processing_time: Optional[float] = None,
        error_message: Optional[str] = None
    ) -> Optional[ASRRequestDB]:
        """Update ASR request status and metadata."""
        try:
            # Query request by ID
            result = await self.db.execute(
                select(ASRRequestDB).where(ASRRequestDB.id == request_id)
            )
            request = result.scalar_one_or_none()
            
            if not request:
                logger.warning(f"ASR request {request_id} not found")
                return None
            
            # Update fields
            request.status = status
            if processing_time is not None:
                request.processing_time = processing_time
            if error_message is not None:
                request.error_message = error_message
            
            await self.db.commit()
            await self.db.refresh(request)
            
            logger.info(f"Updated ASR request {request_id} status to {status}")
            return request
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update ASR request {request_id}: {e}")
            raise DatabaseError(f"Failed to update ASR request: {e}")
    
    async def create_result(
        self,
        request_id: UUID,
        transcript: str,
        confidence_score: Optional[float] = None,
        word_timestamps: Optional[Dict[str, Any]] = None,
        language_detected: Optional[str] = None,
        audio_format: Optional[str] = None,
        sample_rate: Optional[int] = None
    ) -> ASRResultDB:
        """Create new ASR result record."""
        try:
            result = ASRResultDB(
                request_id=request_id,
                transcript=transcript,
                confidence_score=confidence_score,
                word_timestamps=word_timestamps,
                language_detected=language_detected,
                audio_format=audio_format,
                sample_rate=sample_rate
            )
            
            self.db.add(result)
            await self.db.commit()
            await self.db.refresh(result)
            
            logger.info(f"Created ASR result {result.id} for request {request_id}")
            return result
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create ASR result for request {request_id}: {e}")
            raise DatabaseError(f"Failed to create ASR result: {e}")
    
    async def get_request_by_id(self, request_id: UUID) -> Optional[ASRRequestDB]:
        """Get ASR request by ID with eager loading of results."""
        try:
            result = await self.db.execute(
                select(ASRRequestDB)
                .options(selectinload(ASRRequestDB.results))
                .where(ASRRequestDB.id == request_id)
            )
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error(f"Failed to get ASR request {request_id}: {e}")
            raise DatabaseError(f"Failed to get ASR request: {e}")
    
    async def get_requests_by_user(
        self,
        user_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> List[ASRRequestDB]:
        """Get ASR requests by user ID with pagination."""
        try:
            result = await self.db.execute(
                select(ASRRequestDB)
                .where(ASRRequestDB.user_id == user_id)
                .order_by(ASRRequestDB.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"Failed to get ASR requests for user {user_id}: {e}")
            raise DatabaseError(f"Failed to get ASR requests: {e}")
    
    async def get_requests_by_status(
        self,
        status: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[ASRRequestDB]:
        """Get ASR requests by status with pagination."""
        try:
            result = await self.db.execute(
                select(ASRRequestDB)
                .where(ASRRequestDB.status == status)
                .order_by(ASRRequestDB.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"Failed to get ASR requests with status {status}: {e}")
            raise DatabaseError(f"Failed to get ASR requests: {e}")


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
