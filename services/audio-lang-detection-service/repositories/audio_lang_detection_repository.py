"""
Audio Language Detection Repository
Async repository for audio language detection database operations
"""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from models.database_models import AudioLangDetectionRequestDB, AudioLangDetectionResultDB

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom database error"""
    pass


class AudioLangDetectionRepository:
    """Repository for audio language detection database operations"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self._is_tenant_schema: Optional[bool] = None

    async def _is_tenant_context(self) -> bool:
        """
        Check if we're in a tenant schema context by querying search_path.
        Mirrors the pattern used in ASR/NMT repositories.
        """
        if self._is_tenant_schema is not None:
            return self._is_tenant_schema

        try:
            # Query current search_path to detect tenant schema
            result = await self.db.execute(text("SHOW search_path"))
            search_path = result.scalar()

            logger.info(f"AudioLangDetectionRepository checking search_path: {search_path}")

            if search_path:
                # Remove quotes and split by comma
                schemas = [s.strip().strip('"').strip("'") for s in search_path.split(",")]
                logger.info(f"AudioLangDetectionRepository parsed schemas from search_path: {schemas}")
                # If first schema is not 'public' or '$user', assume tenant context
                if schemas and schemas[0] not in ("public", "$user", ""):
                    self._is_tenant_schema = True
                    logger.info(f"AudioLangDetectionRepository detected tenant schema: {schemas[0]}")
                    return True

            self._is_tenant_schema = False
            logger.info(
                "AudioLangDetectionRepository: no tenant schema detected, using public schema. "
                f"search_path was: {search_path}"
            )
            return False
        except Exception as e:
            logger.error(f"AudioLangDetectionRepository: failed to detect tenant context: {e}", exc_info=True)
            # On error, assume non-tenant (public) to avoid breaking inference
            self._is_tenant_schema = False
            return False
    
    async def create_request(
        self,
        model_id: str,
        audio_duration: Optional[float] = None,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ) -> AudioLangDetectionRequestDB:
        """Create new audio language detection request record"""
        try:
            # Log database and search_path for routing verification
            try:
                db_name_result = await self.db.execute(text("SELECT current_database()"))
                current_db = db_name_result.scalar()
                search_path_result = await self.db.execute(text("SHOW search_path"))
                current_search_path = search_path_result.scalar()
                is_tenant = await self._is_tenant_context()
                logger.info(
                    "AudioLangDetectionRepository.create_request: "
                    "database=%s, search_path=%s, is_tenant_schema=%s, model_id=%s, user_id=%s",
                    current_db,
                    current_search_path,
                    is_tenant,
                    model_id,
                    user_id,
                )
            except Exception as log_exc:
                logger.warning(f"AudioLangDetectionRepository: failed to log DB routing info: {log_exc}")

            request = AudioLangDetectionRequestDB(
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id,
                model_id=model_id,
                audio_duration=audio_duration,
                status="processing"
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
        error_message: Optional[str] = None
    ) -> AudioLangDetectionRequestDB:
        """Update audio language detection request status"""
        try:
            stmt = (
                update(AudioLangDetectionRequestDB)
                .where(AudioLangDetectionRequestDB.id == request_id)
                .values(
                    status=status,
                    processing_time=processing_time,
                    error_message=error_message
                )
                .returning(AudioLangDetectionRequestDB)
            )
            
            result = await self.db.execute(stmt)
            await self.db.commit()
            
            request = result.scalar_one_or_none()
            if not request:
                raise DatabaseError(f"Audio language detection request {request_id} not found")
            
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
        all_scores: dict
    ) -> AudioLangDetectionResultDB:
        """Create new audio language detection result record"""
        try:
            # JSONB columns accept Python dict directly, SQLAlchemy handles conversion
            result = AudioLangDetectionResultDB(
                request_id=request_id,
                language_code=language_code,
                confidence=confidence,
                all_scores=all_scores  # dict - SQLAlchemy converts to JSONB
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

