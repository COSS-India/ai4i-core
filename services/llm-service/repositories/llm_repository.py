"""
LLM Repository
Async repository for LLM database operations
"""

import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from models.database_models import LLMRequestDB, LLMResultDB

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom database error"""
    pass


class LLMRepository:
    """Repository for LLM database operations"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_request(
        self,
        model_id: str,
        input_language: Optional[str],
        output_language: Optional[str],
        text_length: int,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ) -> LLMRequestDB:
        """Create new LLM request record"""
        try:
            request = LLMRequestDB(
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id,
                model_id=model_id,
                input_language=input_language,
                output_language=output_language,
                text_length=text_length,
                status="processing"
            )
            
            self.db.add(request)
            await self.db.commit()
            await self.db.refresh(request)
            
            logger.info(f"Created LLM request {request.id}")
            return request
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create LLM request: {e}")
            raise DatabaseError(f"Failed to create LLM request: {e}")
    
    async def update_request_status(
        self,
        request_id: UUID,
        status: str,
        processing_time: Optional[float] = None,
        error_message: Optional[str] = None
    ) -> LLMRequestDB:
        """Update LLM request status"""
        try:
            stmt = (
                update(LLMRequestDB)
                .where(LLMRequestDB.id == request_id)
                .values(
                    status=status,
                    processing_time=processing_time,
                    error_message=error_message
                )
                .returning(LLMRequestDB)
            )
            
            result = await self.db.execute(stmt)
            await self.db.commit()
            
            request = result.scalar_one_or_none()
            if not request:
                raise DatabaseError(f"LLM request {request_id} not found")
            
            logger.info(f"Updated LLM request {request_id} status to {status}")
            return request
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update LLM request {request_id}: {e}")
            raise DatabaseError(f"Failed to update LLM request: {e}")
    
    async def create_result(
        self,
        request_id: UUID,
        output_text: str,
        source_text: str
    ) -> LLMResultDB:
        """Create new LLM result record"""
        try:
            result = LLMResultDB(
                request_id=request_id,
                output_text=output_text,
                source_text=source_text
            )
            
            self.db.add(result)
            await self.db.commit()
            await self.db.refresh(result)
            
            logger.info(f"Created LLM result {result.id} for request {request_id}")
            return result
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create LLM result: {e}")
            raise DatabaseError(f"Failed to create LLM result: {e}")
    
    async def get_request_by_id(self, request_id: UUID) -> Optional[LLMRequestDB]:
        """Get LLM request by ID with results"""
        try:
            stmt = (
                select(LLMRequestDB)
                .options(selectinload(LLMRequestDB.results))
                .where(LLMRequestDB.id == request_id)
            )
            
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error(f"Failed to get LLM request {request_id}: {e}")
            raise DatabaseError(f"Failed to get LLM request: {e}")

