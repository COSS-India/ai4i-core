"""
Speaker Diarization Repository
Async repository for speaker diarization database operations
"""

import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from models.database_models import SpeakerDiarizationRequestDB, SpeakerDiarizationResultDB

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom database error"""
    pass


class SpeakerDiarizationRepository:
    """Repository for speaker diarization database operations"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_request(
        self,
        model_id: str,
        audio_duration: Optional[float] = None,
        num_speakers: Optional[int] = None,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ) -> SpeakerDiarizationRequestDB:
        """Create new speaker diarization request record"""
        try:
            request = SpeakerDiarizationRequestDB(
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id,
                model_id=model_id,
                audio_duration=audio_duration,
                num_speakers=num_speakers,
                status="processing"
            )
            
            self.db.add(request)
            await self.db.commit()
            await self.db.refresh(request)
            
            logger.info(f"Created speaker diarization request {request.id}")
            return request
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create speaker diarization request: {e}")
            raise DatabaseError(f"Failed to create speaker diarization request: {e}")
    
    async def update_request_status(
        self,
        request_id: UUID,
        status: str,
        processing_time: Optional[float] = None,
        error_message: Optional[str] = None
    ) -> SpeakerDiarizationRequestDB:
        """Update speaker diarization request status"""
        try:
            stmt = (
                update(SpeakerDiarizationRequestDB)
                .where(SpeakerDiarizationRequestDB.id == request_id)
                .values(
                    status=status,
                    processing_time=processing_time,
                    error_message=error_message
                )
                .returning(SpeakerDiarizationRequestDB)
            )
            
            result = await self.db.execute(stmt)
            await self.db.commit()
            
            request = result.scalar_one_or_none()
            if not request:
                raise DatabaseError(f"Speaker diarization request {request_id} not found")
            
            logger.info(f"Updated speaker diarization request {request_id} status to {status}")
            return request
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update speaker diarization request {request_id}: {e}")
            raise DatabaseError(f"Failed to update speaker diarization request: {e}")
    
    async def create_result(
        self,
        request_id: UUID,
        total_segments: int,
        num_speakers: int,
        speakers: List[str],
        segments: List[dict]
    ) -> SpeakerDiarizationResultDB:
        """Create new speaker diarization result record"""
        try:
            # JSONB columns accept Python dict/list directly, SQLAlchemy handles conversion
            result = SpeakerDiarizationResultDB(
                request_id=request_id,
                total_segments=total_segments,
                num_speakers=num_speakers,
                speakers=speakers,  # List[str] - SQLAlchemy converts to JSONB
                segments=segments   # List[dict] - SQLAlchemy converts to JSONB
            )
            
            self.db.add(result)
            await self.db.commit()
            await self.db.refresh(result)
            
            logger.info(f"Created speaker diarization result {result.id} for request {request_id}")
            return result
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create speaker diarization result: {e}")
            raise DatabaseError(f"Failed to create speaker diarization result: {e}")
    
    async def get_request_by_id(self, request_id: UUID) -> Optional[SpeakerDiarizationRequestDB]:
        """Get speaker diarization request by ID with results"""
        try:
            stmt = (
                select(SpeakerDiarizationRequestDB)
                .options(selectinload(SpeakerDiarizationRequestDB.results))
                .where(SpeakerDiarizationRequestDB.id == request_id)
            )
            
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error(f"Failed to get speaker diarization request {request_id}: {e}")
            raise DatabaseError(f"Failed to get speaker diarization request: {e}")


async def get_db_session() -> AsyncSession:
    """Dependency function to get database session."""
    from main import db_session_factory
    
    if not db_session_factory:
        raise DatabaseError("Database session factory not initialized")
    
    async with db_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()

