"""
Business logic for model version management.
Handles version validation, creation, and lifecycle operations.
"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from repositories.model_repository import ModelRepository
from models.model_version import ModelVersionCreateRequest
from config import settings
from logger import logger
from fastapi import HTTPException, status


class VersionService:
    """Service for version management business logic."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repository = ModelRepository(db)
    
    async def validate_version_creation(self, model_id: str, version: str) -> None:
        """
        Validate that a new version can be created.
        Checks:
        - Base model exists
        - Version doesn't already exist
        - Active version limit not exceeded
        - Version format is valid
        """
        # Check if base model exists (at least one version should exist)
        existing_versions = await self.repository.find_all_versions(model_id)
        if not existing_versions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Base model with ID {model_id} does not exist. Create the first version using POST /models endpoint."
            )
        
        # Check if version already exists
        if await self.repository.check_version_exists(model_id, version):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Version {version} already exists for model {model_id}"
            )
        
        # Check active version limit
        active_count = await self.repository.count_active_versions(model_id)
        if active_count >= settings.MAX_ACTIVE_VERSIONS_PER_MODEL:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Active version limit ({settings.MAX_ACTIVE_VERSIONS_PER_MODEL}) exceeded for model {model_id}. Deprecate existing versions first."
            )
    
    async def validate_version_update(self, model_id: str, version: str) -> None:
        """Validate that a version can be updated (check immutability)."""
        model = await self.repository.find_by_model_id_and_version(model_id, version)
        if not model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model {model_id} version {version} not found"
            )
        
        if model.is_immutable:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Model {model_id} version {version} is immutable and cannot be modified"
            )
    
    async def get_latest_version(self, model_id: str) -> Optional[str]:
        """Retrieve the most recent active version of a model."""
        model = await self.repository.get_latest_active_version(model_id)
        return model.version if model else None
    
    async def enforce_active_version_limit(self, model_id: str) -> None:
        """
        Auto-deprecate oldest active versions if limit exceeded.
        This is called before creating a new version if limit would be exceeded.
        """
        active_versions = await self.repository.find_active_versions(model_id)
        active_count = len(active_versions)
        
        if active_count >= settings.MAX_ACTIVE_VERSIONS_PER_MODEL:
            # Sort by version (assuming semantic versioning)
            # Deprecate oldest versions first
            versions_to_deprecate = active_versions[settings.MAX_ACTIVE_VERSIONS_PER_MODEL - 1:]
            for model in versions_to_deprecate:
                await self.repository.mark_version_as_deprecated(model_id, model.version)
                logger.info(f"Auto-deprecated model {model_id} version {model.version} to enforce limit")
    
    async def validate_service_version_switch(
        self, 
        model_id: str, 
        new_version: str,
        allow_deprecated: bool = False
    ) -> None:
        """
        Validate that a service can switch to a new model version.
        Checks:
        - New version exists
        - New version is not deprecated (or allowed by config)
        """
        model = await self.repository.find_by_model_id_and_version(model_id, new_version)
        if not model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model {model_id} version {new_version} not found"
            )
        
        if model.version_status == "deprecated" and not allow_deprecated:
            if not settings.ALLOW_SERVICE_DEPRECATED_VERSION_SWITCH:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Version {new_version} is deprecated and cannot be used for services"
                )

