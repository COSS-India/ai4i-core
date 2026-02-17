"""
OCR repository utilities.

Provides database session dependency hook and CRUD operations for OCR requests and results.
"""

import logging
from uuid import UUID
from typing import AsyncGenerator, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models.database_models import OCRRequestDB, OCRResultDB

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom database error for repository operations."""


class OCRRepository:
    """Async repository for OCR database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_request(
        self,
        model_id: str,
        language: str,
        image_count: Optional[int] = None,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ) -> OCRRequestDB:
        """Create new OCR request record."""
        try:
            # Verify search_path and database connection (like ASR service does)
            from sqlalchemy import text
            result = await self.db.execute(text("SHOW search_path"))
            current_search_path = result.scalar()
            result_db = await self.db.execute(text("SELECT current_database()"))
            current_db = result_db.scalar()
            logger.info(f"OCRRepository.create_request: database={current_db}, search_path={current_search_path}, model_id={model_id}, user_id={user_id}")
            
            request = OCRRequestDB(
                model_id=model_id,
                language=language,
                image_count=image_count,
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id,
                status="processing"
            )
            
            self.db.add(request)
            await self.db.commit()
            await self.db.refresh(request)
            
            logger.info(f"Created OCR request {request.id} for model {model_id} in database={current_db}, schema={current_search_path}")
            return request
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create OCR request: {e}")
            raise DatabaseError(f"Failed to create OCR request: {e}")
    
    async def update_request_status(
        self,
        request_id: UUID,
        status: str,
        processing_time: Optional[float] = None,
        error_message: Optional[str] = None
    ) -> Optional[OCRRequestDB]:
        """Update OCR request status and metadata."""
        try:
            # Query request by ID
            result = await self.db.execute(
                select(OCRRequestDB).where(OCRRequestDB.id == request_id)
            )
            request = result.scalar_one_or_none()
            
            if not request:
                logger.warning(f"OCR request {request_id} not found")
                return None
            
            # Update fields
            request.status = status
            if processing_time is not None:
                request.processing_time = processing_time
            if error_message is not None:
                request.error_message = error_message
            
            await self.db.commit()
            await self.db.refresh(request)
            
            logger.info(f"Updated OCR request {request_id} status to {status}")
            return request
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update OCR request {request_id}: {e}")
            raise DatabaseError(f"Failed to update OCR request: {e}")
    
    async def create_result(
        self,
        request_id: UUID,
        extracted_text: str,
        page_count: Optional[int] = None
    ) -> OCRResultDB:
        """Create new OCR result record."""
        try:
            result = OCRResultDB(
                request_id=request_id,
                extracted_text=extracted_text,
                page_count=page_count
            )
            
            self.db.add(result)
            await self.db.commit()
            await self.db.refresh(result)
            
            logger.info(f"Created OCR result {result.id} for request {request_id}")
            return result
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create OCR result for request {request_id}: {e}")
            raise DatabaseError(f"Failed to create OCR result: {e}")
    
    async def get_request_by_id(self, request_id: UUID) -> Optional[OCRRequestDB]:
        """Get OCR request by ID with eager loading of results."""
        try:
            result = await self.db.execute(
                select(OCRRequestDB)
                .options(selectinload(OCRRequestDB.results))
                .where(OCRRequestDB.id == request_id)
            )
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error(f"Failed to get OCR request {request_id}: {e}")
            raise DatabaseError(f"Failed to get OCR request: {e}")
    
    async def get_requests_by_user(
        self,
        user_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> List[OCRRequestDB]:
        """Get OCR requests by user ID with pagination."""
        try:
            result = await self.db.execute(
                select(OCRRequestDB)
                .where(OCRRequestDB.user_id == user_id)
                .order_by(OCRRequestDB.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"Failed to get OCR requests for user {user_id}: {e}")
            raise DatabaseError(f"Failed to get OCR requests: {e}")


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function to get a database session from the global factory.
    DEPRECATED: Use get_tenant_db_session from middleware.tenant_db_dependency instead.
    """
    from main import db_session_factory

    if not db_session_factory:
        raise DatabaseError("Database session factory not initialized")

    async with db_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()

