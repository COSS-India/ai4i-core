"""
NMT Repository
Async repository for NMT database operations
"""

import logging
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from models.database_models import NMTRequestDB, NMTResultDB

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom database error"""
    pass


class NMTRepository:
    """Repository for NMT database operations"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_request(
        self,
        model_id: str,
        source_language: str,
        target_language: str,
        text_length: int,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ) -> NMTRequestDB:
        """Create new NMT request record"""
        try:
            request = NMTRequestDB(
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id,
                model_id=model_id,
                source_language=source_language,
                target_language=target_language,
                text_length=text_length,
                status="processing"
            )
            
            self.db.add(request)
            await self.db.commit()
            await self.db.refresh(request)
            
            logger.info(f"Created NMT request {request.id}")
            return request
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create NMT request: {e}")
            raise DatabaseError(f"Failed to create NMT request: {e}")
    
    async def update_request_status(
        self,
        request_id: UUID,
        status: str,
        processing_time: Optional[float] = None,
        error_message: Optional[str] = None
    ) -> NMTRequestDB:
        """Update NMT request status"""
        try:
            stmt = (
                update(NMTRequestDB)
                .where(NMTRequestDB.id == request_id)
                .values(
                    status=status,
                    processing_time=processing_time,
                    error_message=error_message
                )
                .returning(NMTRequestDB)
            )
            
            result = await self.db.execute(stmt)
            await self.db.commit()
            
            request = result.scalar_one_or_none()
            if not request:
                raise DatabaseError(f"NMT request {request_id} not found")
            
            logger.info(f"Updated NMT request {request_id} status to {status}")
            return request
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update NMT request {request_id}: {e}")
            raise DatabaseError(f"Failed to update NMT request: {e}")
    
    async def create_result(
        self,
        request_id: UUID,
        translated_text: str,
        source_text: str,
        confidence_score: Optional[float] = None,
        language_detected: Optional[str] = None,
        word_alignments: Optional[Dict[str, Any]] = None
    ) -> NMTResultDB:
        """Create new NMT result record"""
        try:
            result = NMTResultDB(
                request_id=request_id,
                translated_text=translated_text,
                source_text=source_text,
                confidence_score=confidence_score,
                language_detected=language_detected,
                word_alignments=word_alignments
            )
            
            self.db.add(result)
            await self.db.commit()
            await self.db.refresh(result)
            
            logger.info(f"Created NMT result {result.id} for request {request_id}")
            return result
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create NMT result: {e}")
            raise DatabaseError(f"Failed to create NMT result: {e}")
    
    async def get_request_by_id(self, request_id: UUID) -> Optional[NMTRequestDB]:
        """Get NMT request by ID with results"""
        try:
            stmt = (
                select(NMTRequestDB)
                .options(selectinload(NMTRequestDB.results))
                .where(NMTRequestDB.id == request_id)
            )
            
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error(f"Failed to get NMT request {request_id}: {e}")
            raise DatabaseError(f"Failed to get NMT request: {e}")
    
    async def get_requests_by_user(
        self,
        user_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> List[NMTRequestDB]:
        """Get NMT requests by user with pagination"""
        try:
            stmt = (
                select(NMTRequestDB)
                .where(NMTRequestDB.user_id == user_id)
                .order_by(NMTRequestDB.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            
            result = await self.db.execute(stmt)
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"Failed to get NMT requests for user {user_id}: {e}")
            raise DatabaseError(f"Failed to get NMT requests: {e}")
