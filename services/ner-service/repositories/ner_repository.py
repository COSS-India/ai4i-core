"""
NER repository utilities.

Provides database session dependency hook and CRUD operations for NER requests and results.
"""

import logging
from uuid import UUID
from typing import AsyncGenerator, Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models.database_models import NERRequestDB, NERResultDB

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom database error for repository operations."""


class NERRepository:
    """Async repository for NER database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_request(
        self,
        model_id: str,
        language: str,
        text_length: Optional[int] = None,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ) -> NERRequestDB:
        """Create new NER request record."""
        try:
            request = NERRequestDB(
                model_id=model_id,
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
            
            logger.info(f"Created NER request {request.id} for model {model_id}")
            return request
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create NER request: {e}")
            raise DatabaseError(f"Failed to create NER request: {e}")
    
    async def update_request_status(
        self,
        request_id: UUID,
        status: str,
        processing_time: Optional[float] = None,
        error_message: Optional[str] = None
    ) -> Optional[NERRequestDB]:
        """Update NER request status and metadata."""
        try:
            # Query request by ID
            result = await self.db.execute(
                select(NERRequestDB).where(NERRequestDB.id == request_id)
            )
            request = result.scalar_one_or_none()
            
            if not request:
                logger.warning(f"NER request {request_id} not found")
                return None
            
            # Update fields
            request.status = status
            if processing_time is not None:
                request.processing_time = processing_time
            if error_message is not None:
                request.error_message = error_message
            
            await self.db.commit()
            await self.db.refresh(request)
            
            logger.info(f"Updated NER request {request_id} status to {status}")
            return request
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update NER request {request_id}: {e}")
            raise DatabaseError(f"Failed to update NER request: {e}")
    
    async def create_result(
        self,
        request_id: UUID,
        entities: Dict[str, Any],
        source_text: Optional[str] = None
    ) -> NERResultDB:
        """Create new NER result record."""
        try:
            result = NERResultDB(
                request_id=request_id,
                entities=entities,
                source_text=source_text
            )
            
            self.db.add(result)
            await self.db.commit()
            await self.db.refresh(result)
            
            logger.info(f"Created NER result {result.id} for request {request_id}")
            return result
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create NER result for request {request_id}: {e}")
            raise DatabaseError(f"Failed to create NER result: {e}")
    
    async def get_request_by_id(self, request_id: UUID) -> Optional[NERRequestDB]:
        """Get NER request by ID with eager loading of results."""
        try:
            result = await self.db.execute(
                select(NERRequestDB)
                .options(selectinload(NERRequestDB.results))
                .where(NERRequestDB.id == request_id)
            )
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error(f"Failed to get NER request {request_id}: {e}")
            raise DatabaseError(f"Failed to get NER request: {e}")
    
    async def get_requests_by_user(
        self,
        user_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> List[NERRequestDB]:
        """Get NER requests by user ID with pagination."""
        try:
            result = await self.db.execute(
                select(NERRequestDB)
                .where(NERRequestDB.user_id == user_id)
                .order_by(NERRequestDB.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"Failed to get NER requests for user {user_id}: {e}")
            raise DatabaseError(f"Failed to get NER requests: {e}")


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function to get a database session from the global factory.
    """
    from main import db_session_factory

    if not db_session_factory:
        raise DatabaseError("Database session factory not initialized")

    async with db_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
