"""
Async repository for ASR database operations.

Adapted from Dhruva-Platform-2 PostgreSQLBaseRepository for async SQLAlchemy.
"""

import logging
from uuid import UUID
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, text

from sqlalchemy.orm import selectinload

# Import public schema models (for non-tenant users)
from models.database_models import ASRRequestDB as PublicASRRequestDB, ASRResultDB as PublicASRResultDB

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
    # Try Docker path first
    docker_path = '/app/services/multi-tenant-feature'
    if os.path.exists(docker_path):
        if docker_path not in sys.path:
            sys.path.insert(0, docker_path)
    else:
        # Try local dev path
        workspace_root = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))
        multi_tenant_path = os.path.join(workspace_root, 'services', 'multi-tenant-feature')
        if os.path.exists(multi_tenant_path) and multi_tenant_path not in sys.path:
            sys.path.insert(0, multi_tenant_path)
    from models.service_schema_models import ASRRequestDB as TenantASRRequestDB, ASRResultDB as TenantASRResultDB
    logger.info(f"Successfully imported tenant schema models from {docker_path if os.path.exists(docker_path) else multi_tenant_path}")
except (ImportError, ValueError) as e:
    # Fallback if tenant models not available
    logger.warning(f"Could not import tenant schema models: {e}, will use public schema models", exc_info=True)
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
            # Query current search_path to detect tenant schema
            result = await self.db.execute(text("SHOW search_path"))
            search_path = result.scalar()
            
            logger.info(f"Repository checking search_path: {search_path}")
            
            # If search_path contains a schema other than 'public' or '$user', we're in tenant context
            # Tenant schemas are typically named like 'tenant_123' or similar
            # The search_path format is: "schema_name", public or schema_name, public
            if search_path:
                # Remove quotes and split by comma
                schemas = [s.strip().strip('"').strip("'") for s in search_path.split(',')]
                logger.info(f"Parsed schemas from search_path: {schemas}")
                # Check if first schema is not 'public' or '$user'
                if schemas and schemas[0] not in ('public', '$user', ''):
                    # Additional check: tenant schemas usually don't start with these patterns
                    first_schema = schemas[0]
                    if first_schema and first_schema != 'public':
                        self._is_tenant_schema = True
                        logger.info(f"Detected tenant schema: {first_schema}")
                        return True
            
            self._is_tenant_schema = False
            logger.info(f"No tenant schema detected, using public schema. search_path was: {search_path}")
            return False
        except Exception as e:
            logger.error(f"Could not determine tenant context: {e}, defaulting to public schema", exc_info=True)
            self._is_tenant_schema = False
            return False
    
    
    def _get_tenant_models(self):
        """Lazy import of tenant models to avoid startup issues."""
        # First check if module-level import succeeded
        if TenantASRRequestDB is not None:
            return TenantASRRequestDB, TenantASRResultDB
        
        # Try to import on demand
        try:
            import sys
            import os
            docker_path = '/app/services/multi-tenant-feature'
            if os.path.exists(docker_path):
                # Ensure the path is in sys.path for imports to work
                if docker_path not in sys.path:
                    sys.path.insert(0, docker_path)
                logger.info(f"Attempting to import tenant models from {docker_path}, sys.path includes: {docker_path in sys.path}")
                
                # Try regular import first (should work now that path is set)
                try:
                    from models.service_schema_models import ASRRequestDB, ASRResultDB
                    logger.info(f"Successfully imported tenant models on demand: {ASRRequestDB.__name__}")
                    return ASRRequestDB, ASRResultDB
                except ImportError as import_err:
                    logger.warning(f"Regular import failed: {import_err}, trying importlib")
                    # Fallback to importlib if regular import fails
                    import importlib.util
                    spec = importlib.util.spec_from_file_location(
                        "service_schema_models",
                        "/app/services/multi-tenant-feature/models/service_schema_models.py"
                    )
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        # Set __package__ and __path__ to help with relative imports
                        module.__package__ = 'models'
                        spec.loader.exec_module(module)
                        ASRRequestDB = module.ASRRequestDB
                        ASRResultDB = module.ASRResultDB
                        logger.info(f"Successfully imported tenant models via importlib: {ASRRequestDB.__name__}")
                        return ASRRequestDB, ASRResultDB
            else:
                logger.warning(f"Multi-tenant-feature path does not exist: {docker_path}")
        except Exception as e:
            logger.error(f"Could not import tenant models on demand: {e}", exc_info=True)
        return None, None
    
    async def create_request(
        self,
        model_id: str,
        language: str,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ):
        """Create new ASR request record."""
        try:
            # Use tenant schema models if in tenant context
            logger.info(f"ASRRepository.create_request called: model_id={model_id}, user_id={user_id}")
            is_tenant = await self._is_tenant_context()
            
            # Get tenant models if needed
            TenantRequestModel, TenantResultModel = self._get_tenant_models() if is_tenant else (None, None)
            RequestModel = TenantRequestModel if (is_tenant and TenantRequestModel) else PublicASRRequestDB
            
            logger.info(f"Using RequestModel: {RequestModel.__name__}, is_tenant={is_tenant}, TenantASRRequestDB available={TenantRequestModel is not None}")
            
            request = RequestModel(
                model_id=model_id,
                language=language,
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id,
                status="processing"
            )
            
            # Log table info before adding
            table_name = RequestModel.__table__.name
            table_schema = RequestModel.__table__.schema
            logger.info(f"About to create request: table={table_name}, schema={table_schema}, model={RequestModel.__name__}, is_tenant={is_tenant}")
            
            # Verify search_path and database connection
            result = await self.db.execute(text("SHOW search_path"))
            current_search_path = result.scalar()
            result_db = await self.db.execute(text("SELECT current_database()"))
            current_db = result_db.scalar()
            logger.info(f"Current database: {current_db}, search_path before insert: {current_search_path}")
            
            self.db.add(request)
            await self.db.commit()
            await self.db.refresh(request)
            
            logger.info(f"Created ASR request {request.id} for model {model_id} (tenant_schema={is_tenant}, RequestModel={RequestModel.__name__}, table={table_name})")
            return request
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create ASR request: {e}", exc_info=True)
            raise DatabaseError(f"Failed to create ASR request: {e}")
    
    async def update_request_status(
        self,
        request_id: UUID,
        status: str,
        processing_time: Optional[float] = None,
        error_message: Optional[str] = None
    ):
        """Update ASR request status and metadata."""
        try:
            # Use tenant schema models if in tenant context
            is_tenant = await self._is_tenant_context()
            RequestModel = TenantASRRequestDB if (is_tenant and TenantASRRequestDB) else PublicASRRequestDB
            
            # Query request by ID
            result = await self.db.execute(
                select(RequestModel).where(RequestModel.id == request_id)
            )
            request = result.scalar_one_or_none()
            
            if not request:
                logger.warning(f"ASR request {request_id} not found")
                return None
            
            # Update fields
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
        sample_rate: Optional[int] = None
    ):
        """Create new ASR result record."""
        try:
            # Use tenant schema models if in tenant context
            is_tenant = await self._is_tenant_context()
            ResultModel = TenantASRResultDB if (is_tenant and TenantASRResultDB) else PublicASRResultDB
            
            result = ResultModel(
                request_id=request_id,
                transcript=transcript,
                confidence_score=confidence_score,
                word_timestamps=word_timestamps,
                language_detected=language_detected,
                audio_format=audio_format,
                sample_rate=sample_rate
            )
            
            self.db.add(result)
            await self.db.commit()
            await self.db.refresh(result)
            
            logger.info(f"Created ASR result {result.id} for request {request_id} (tenant_schema={is_tenant})")
            return result
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create ASR result for request {request_id}: {e}")
            raise DatabaseError(f"Failed to create ASR result: {e}")
    
    async def get_request_by_id(self, request_id: UUID):
        """Get ASR request by ID with eager loading of results."""
        try:
            # Use tenant schema models if in tenant context
            is_tenant = await self._is_tenant_context()
            RequestModel = TenantASRRequestDB if (is_tenant and TenantASRRequestDB) else PublicASRRequestDB
            
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
        offset: int = 0
    ):
        """Get ASR requests by user ID with pagination."""
        try:
            # Use tenant schema models if in tenant context
            is_tenant = await self._is_tenant_context()
            RequestModel = TenantASRRequestDB if (is_tenant and TenantASRRequestDB) else PublicASRRequestDB
            
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
        offset: int = 0
    ):
        """Get ASR requests by status with pagination."""
        try:
            # Use tenant schema models if in tenant context
            is_tenant = await self._is_tenant_context()
            RequestModel = TenantASRRequestDB if (is_tenant and TenantASRRequestDB) else PublicASRRequestDB
            
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


async def get_db_session() -> AsyncSession:
    """Dependency function to get database session."""
    # This will be injected by FastAPI dependency injection
    # The actual session will be provided by the main app
    from main import db_session_factory
    
    if not db_session_factory:
        raise DatabaseError("Database session factory not initialized")
    
    async with db_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
