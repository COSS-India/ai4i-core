"""
Async repository for ASR database operations.
"""

import logging
from uuid import UUID
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.asr import ASRRequestDB, ASRResultDB

# Use structured logging if available
try:
    from ai4icore_logging import get_logger
    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)

# Import tenant schema models (for tenant users)
try:
    import sys
    import os
    # In Docker, multi-tenant-feature is at /app/services/multi-tenant-feature
    # In local dev, it's at services/multi-tenant-feature relative to workspace root
    current_dir = os.path.dirname(os.path.abspath(__file__))
    docker_path = '/app/services/multi-tenant-feature'
    if os.path.exists(docker_path):
        if docker_path not in sys.path:
            sys.path.append(docker_path)
    else:
        workspace_root = os.path.abspath(os.path.join(current_dir, '..', '..', '..', '..'))
        multi_tenant_path = os.path.join(workspace_root, 'services', 'multi-tenant-feature')
        if os.path.exists(multi_tenant_path) and multi_tenant_path not in sys.path:
            sys.path.append(multi_tenant_path)
    from models.service_schema_models import ASRRequestDB as TenantASRRequestDB, ASRResultDB as TenantASRResultDB
except (ImportError, ValueError) as e:
    logger.warning(f"Could not import tenant schema models: {e}, will use public schema models")
    TenantASRRequestDB = None
    TenantASRResultDB = None


class DatabaseError(Exception):
    """Custom exception for database operations."""
    pass


class ASRRepository:
    """Async repository for ASR database operations."""

    def __init__(self, db: AsyncSession):
        """Initialize repository with async database session."""
        self.db = db
        self._is_tenant_schema = None  # Cache for tenant schema detection

    async def _is_tenant_context(self) -> bool:
        """Check if we're in a tenant schema context by querying search_path."""
        if self._is_tenant_schema is not None:
            return self._is_tenant_schema

        try:
            from sqlalchemy import text
            result = await self.db.execute(text("SHOW search_path"))
            search_path = result.scalar()

            if search_path:
                schemas = [s.strip().strip('"').strip("'") for s in search_path.split(',')]
                if schemas and schemas[0] not in ('public', '$user', ''):
                    first_schema = schemas[0]
                    if first_schema and first_schema != 'public':
                        self._is_tenant_schema = True
                        logger.info(f"Detected tenant schema: {first_schema}")
                        return True

            self._is_tenant_schema = False
            return False
        except Exception as e:
            logger.error(f"Could not determine tenant context: {e}, defaulting to public schema")
            self._is_tenant_schema = False
            return False

    def _get_tenant_models(self):
        """Lazy import of tenant models to avoid startup issues."""
        if TenantASRRequestDB is not None:
            return TenantASRRequestDB, TenantASRResultDB

        try:
            import importlib.util
            docker_path = '/app/services/multi-tenant-feature'
            if os.path.exists(docker_path):
                if docker_path not in sys.path:
                    sys.path.append(docker_path)
                try:
                    from models.service_schema_models import ASRRequestDB as _TReq, ASRResultDB as _TRes
                    return _TReq, _TRes
                except ImportError:
                    spec = importlib.util.spec_from_file_location(
                        "service_schema_models",
                        "/app/services/multi-tenant-feature/models/service_schema_models.py"
                    )
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        module.__package__ = 'models'
                        spec.loader.exec_module(module)
                        return module.ASRRequestDB, module.ASRResultDB
        except Exception as e:
            logger.error(f"Could not import tenant models on demand: {e}")
        return None, None

    async def create_request(
        self,
        model_id: str,
        language: str,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
        status: str = "processing",
    ):
        """Create new ASR request record."""
        try:
            is_tenant = await self._is_tenant_context()
            TenantRequestModel, _ = self._get_tenant_models() if is_tenant else (None, None)
            RequestModel = TenantRequestModel if (is_tenant and TenantRequestModel) else ASRRequestDB

            request = RequestModel(
                model_id=model_id,
                language=language,
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id,
                status=status,
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
        error_message: Optional[str] = None,
    ):
        """Update ASR request status and metadata."""
        try:
            is_tenant = await self._is_tenant_context()
            RequestModel = TenantASRRequestDB if (is_tenant and TenantASRRequestDB) else ASRRequestDB

            result = await self.db.execute(
                select(RequestModel).where(RequestModel.id == request_id)
            )
            request = result.scalar_one_or_none()

            if not request:
                logger.warning(f"ASR request {request_id} not found")
                return None

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
        sample_rate: Optional[int] = None,
    ):
        """Create new ASR result record."""
        try:
            is_tenant = await self._is_tenant_context()
            ResultModel = TenantASRResultDB if (is_tenant and TenantASRResultDB) else ASRResultDB

            result = ResultModel(
                request_id=request_id,
                transcript=transcript,
                confidence_score=confidence_score,
                word_timestamps=word_timestamps,
                language_detected=language_detected,
                audio_format=audio_format,
                sample_rate=sample_rate,
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

    async def get_request_by_id(self, request_id: UUID):
        """Get ASR request by ID with eager loading of results."""
        try:
            is_tenant = await self._is_tenant_context()
            RequestModel = TenantASRRequestDB if (is_tenant and TenantASRRequestDB) else ASRRequestDB

            result = await self.db.execute(
                select(RequestModel)
                .options(selectinload(RequestModel.results))
                .where(RequestModel.id == request_id)
            )
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"Failed to get ASR request {request_id}: {e}")
            raise DatabaseError(f"Failed to get ASR request: {e}")

    async def get_requests_by_user(
        self,
        user_id: int,
        limit: int = 100,
        offset: int = 0,
    ):
        """Get ASR requests by user ID with pagination."""
        try:
            is_tenant = await self._is_tenant_context()
            RequestModel = TenantASRRequestDB if (is_tenant and TenantASRRequestDB) else ASRRequestDB

            result = await self.db.execute(
                select(RequestModel)
                .where(RequestModel.user_id == user_id)
                .order_by(RequestModel.created_at.desc())
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
        offset: int = 0,
    ):
        """Get ASR requests by status with pagination."""
        try:
            is_tenant = await self._is_tenant_context()
            RequestModel = TenantASRRequestDB if (is_tenant and TenantASRRequestDB) else ASRRequestDB

            result = await self.db.execute(
                select(RequestModel)
                .where(RequestModel.status == status)
                .order_by(RequestModel.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return result.scalars().all()

        except Exception as e:
            logger.error(f"Failed to get ASR requests with status {status}: {e}")
            raise DatabaseError(f"Failed to get ASR requests: {e}")
