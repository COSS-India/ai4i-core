"""
Audio Language Detection repository utilities.

Provides CRUD operations for audio language detection requests and results.
"""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.models.audio_lang_detection import AudioLangDetectionRequestDB, AudioLangDetectionResultDB

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom database error for repository operations."""


class AudioLangDetectionRepository:
    """Async repository for audio language detection database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_request(
        self,
        model_id: str,
        audio_duration: Optional[float] = None,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
    ) -> AudioLangDetectionRequestDB:
        """Create new audio language detection request record."""
        try:
            request = AudioLangDetectionRequestDB(
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id,
                model_id=model_id,
                audio_duration=audio_duration,
                status="processing",
            )

            self.db.add(request)
            await self.db.commit()
            await self.db.refresh(request)

            logger.info(f"Created audio language detection request {request.id}")
            return request

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create audio language detection request: {e}")
            raise DatabaseError(f"Failed to create audio language detection request: {e}")

    async def update_request_status(
        self,
        request_id: UUID,
        status: str,
        processing_time: Optional[float] = None,
        error_message: Optional[str] = None,
    ) -> Optional[AudioLangDetectionRequestDB]:
        """Update audio language detection request status."""
        try:
            stmt = (
                update(AudioLangDetectionRequestDB)
                .where(AudioLangDetectionRequestDB.id == request_id)
                .values(
                    status=status,
                    processing_time=processing_time,
                    error_message=error_message,
                )
                .returning(AudioLangDetectionRequestDB)
            )

            result = await self.db.execute(stmt)
            await self.db.commit()

            request = result.scalar_one_or_none()
            if not request:
                logger.warning(f"Audio language detection request {request_id} not found")
                return None

            logger.info(f"Updated audio language detection request {request_id} status to {status}")
            return request

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update audio language detection request {request_id}: {e}")
            raise DatabaseError(f"Failed to update audio language detection request: {e}")

    async def create_result(
        self,
        request_id: UUID,
        language_code: str,
        confidence: float,
        all_scores: dict,
    ) -> AudioLangDetectionResultDB:
        """Create new audio language detection result record."""
        try:
            result = AudioLangDetectionResultDB(
                request_id=request_id,
                language_code=language_code,
                confidence=confidence,
                all_scores=all_scores,
            )

            self.db.add(result)
            await self.db.commit()
            await self.db.refresh(result)

            logger.info(f"Created audio language detection result {result.id} for request {request_id}")
            return result

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create audio language detection result: {e}")
            raise DatabaseError(f"Failed to create audio language detection result: {e}")

    async def get_request_by_id(self, request_id: UUID) -> Optional[AudioLangDetectionRequestDB]:
        """Get audio language detection request by ID with eager loading of results."""
        try:
            result = await self.db.execute(
                select(AudioLangDetectionRequestDB)
                .options(selectinload(AudioLangDetectionRequestDB.results))
                .where(AudioLangDetectionRequestDB.id == request_id)
            )
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"Failed to get audio language detection request {request_id}: {e}")
            raise DatabaseError(f"Failed to get audio language detection request: {e}")
