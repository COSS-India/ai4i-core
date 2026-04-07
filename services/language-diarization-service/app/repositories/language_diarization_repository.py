"""Language Diarization repository -- async CRUD operations."""

import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.models.language_diarization import LanguageDiarizationRequestDB, LanguageDiarizationResultDB

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom database error."""
    pass


class LanguageDiarizationRepository:
    """Repository for language diarization database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_request(
        self,
        model_id: str,
        audio_duration: Optional[float] = None,
        target_language: Optional[str] = None,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
    ) -> LanguageDiarizationRequestDB:
        """Create new language diarization request record."""
        try:
            request = LanguageDiarizationRequestDB(
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id,
                model_id=model_id,
                audio_duration=audio_duration,
                target_language=target_language,
                status="processing",
            )
            self.db.add(request)
            await self.db.flush()
            await self.db.commit()
            await self.db.refresh(request)
            logger.info(f"Created language diarization request {request.id}")
            return request
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create language diarization request: {e}", exc_info=True)
            raise DatabaseError(f"Failed to create language diarization request: {e}")

    async def update_request_status(
        self,
        request_id: UUID,
        status: str,
        processing_time: Optional[float] = None,
        error_message: Optional[str] = None,
    ) -> LanguageDiarizationRequestDB:
        """Update language diarization request status."""
        try:
            stmt = (
                update(LanguageDiarizationRequestDB)
                .where(LanguageDiarizationRequestDB.id == request_id)
                .values(
                    status=status,
                    processing_time=processing_time,
                    error_message=error_message,
                )
                .returning(LanguageDiarizationRequestDB)
            )
            result = await self.db.execute(stmt)
            await self.db.commit()
            request = result.scalar_one_or_none()
            if not request:
                raise DatabaseError(f"Language diarization request {request_id} not found")
            logger.info(f"Updated language diarization request {request_id} status to {status}")
            return request
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update language diarization request {request_id}: {e}")
            raise DatabaseError(f"Failed to update language diarization request: {e}")

    async def create_result(
        self,
        request_id: UUID,
        total_segments: int,
        segments: List[dict],
        target_language: Optional[str] = None,
    ) -> LanguageDiarizationResultDB:
        """Create new language diarization result record."""
        try:
            result = LanguageDiarizationResultDB(
                request_id=request_id,
                total_segments=total_segments,
                segments=segments,
                target_language=target_language,
            )
            self.db.add(result)
            await self.db.flush()
            await self.db.commit()
            await self.db.refresh(result)
            logger.info(f"Created language diarization result {result.id} for request {request_id}")
            return result
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create language diarization result: {e}", exc_info=True)
            raise DatabaseError(f"Failed to create language diarization result: {e}")
