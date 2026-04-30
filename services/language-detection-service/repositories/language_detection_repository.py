import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from models.database_models import LanguageDetectionRequestDB, LanguageDetectionResultDB

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    pass


class LanguageDetectionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_request(
        self,
        model_id: str,
        text_length: int,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ) -> LanguageDetectionRequestDB:
        try:
            request = LanguageDetectionRequestDB(
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id,
                model_id=model_id,
                text_length=text_length,
                status="processing"
            )
            self.db.add(request)
            await self.db.commit()
            await self.db.refresh(request)
            logger.info(f"Created language detection request {request.id}")
            return request
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create language detection request: {e}")
            raise DatabaseError(f"Failed to create language detection request: {e}")

    async def update_request_status(
        self,
        request_id: UUID,
        status: str,
        processing_time: Optional[float] = None,
        error_message: Optional[str] = None
    ) -> LanguageDetectionRequestDB:
        try:
            stmt = (
                update(LanguageDetectionRequestDB)
                .where(LanguageDetectionRequestDB.id == request_id)
                .values(
                    status=status,
                    processing_time=processing_time,
                    error_message=error_message
                )
                .returning(LanguageDetectionRequestDB)
            )
            result = await self.db.execute(stmt)
            await self.db.commit()
            request = result.scalar_one_or_none()
            if not request:
                raise DatabaseError(f"Language detection request {request_id} not found")
            logger.info(f"Updated language detection request {request_id} status to {status}")
            return request
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update language detection request {request_id}: {e}")
            raise DatabaseError(f"Failed to update language detection request: {e}")

    async def create_result(
        self,
        request_id: UUID,
        source_text: str,
        detected_language: str,
        detected_script: str,
        confidence_score: float,
        language_name: str
    ) -> LanguageDetectionResultDB:
        try:
            result = LanguageDetectionResultDB(
                request_id=request_id,
                source_text=source_text,
                detected_language=detected_language,
                detected_script=detected_script,
                confidence_score=confidence_score,
                language_name=language_name
            )
            self.db.add(result)
            await self.db.commit()
            await self.db.refresh(result)
            logger.info(f"Created language detection result {result.id} for request {request_id}")
            return result
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create language detection result: {e}")
            raise DatabaseError(f"Failed to create language detection result: {e}")

    async def get_request_by_id(self, request_id: UUID) -> Optional[LanguageDetectionRequestDB]:
        try:
            stmt = (
                select(LanguageDetectionRequestDB)
                .options(selectinload(LanguageDetectionRequestDB.results))
                .where(LanguageDetectionRequestDB.id == request_id)
            )
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get language detection request {request_id}: {e}")
            raise DatabaseError(f"Failed to get language detection request: {e}")


async def get_db_session() -> AsyncSession:
    from main import db_session_factory
    if not db_session_factory:
        raise DatabaseError("Database session factory not initialized")
    async with db_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
