"""
Business logic for service-version operations and switching.
Handles service version management and impact analysis.
"""
from typing import List, Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.db_models import Service, Model
from repositories.model_repository import ModelRepository
from services.version_service import VersionService
from config import settings
from logger import logger
from fastapi import HTTPException, status
import time


class ServiceVersionService:
    """Service for service-version operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.model_repository = ModelRepository(db)
        self.version_service = VersionService(db)
    
    async def get_available_versions_for_service(self, service_id: str) -> List[str]:
        """List all versions of the model that a service can switch to."""
        # Get the service to find its current model_id
        stmt = select(Service).where(Service.service_id == service_id)
        result = await self.db.execute(stmt)
        service = result.scalar_one_or_none()
        
        if not service:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service {service_id} not found"
            )
        
        # Get all versions of the model
        versions = await self.model_repository.find_all_versions(service.model_id)
        return [v.version for v in versions]
    
    async def get_services_impact(self, model_id: str, version: str) -> List[Dict[str, Any]]:
        """
        Identify all services using a specific model version.
        Used for impact analysis when deprecating or deleting versions.
        """
        stmt = select(Service).where(
            Service.model_id == model_id,
            Service.model_version == version
        )
        result = await self.db.execute(stmt)
        services = result.scalars().all()
        
        return [
            {
                "serviceId": s.service_id,
                "name": s.name,
                "endpoint": s.endpoint
            }
            for s in services
        ]
    
    async def validate_version_switch(
        self, 
        service_id: str, 
        new_version: str
    ) -> None:
        """Validate that a service can switch to a new version."""
        # Get the service
        stmt = select(Service).where(Service.service_id == service_id)
        result = await self.db.execute(stmt)
        service = result.scalar_one_or_none()
        
        if not service:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service {service_id} not found"
            )
        
        # Validate the new version
        allow_deprecated = settings.ALLOW_SERVICE_DEPRECATED_VERSION_SWITCH
        await self.version_service.validate_service_version_switch(
            service.model_id,
            new_version,
            allow_deprecated=allow_deprecated
        )
    
    async def switch_service_version(
        self, 
        service_id: str, 
        new_version: str,
        user_id: Optional[int] = None
    ) -> bool:
        """
        Perform version switch for a service with logging.
        Returns True if successful.
        """
        stmt = select(Service).where(Service.service_id == service_id)
        result = await self.db.execute(stmt)
        service = result.scalar_one_or_none()
        
        if not service:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service {service_id} not found"
            )
        
        old_version = service.model_version
        
        # Validate switch
        await self.validate_version_switch(service_id, new_version)
        
        # Perform switch
        service.model_version = new_version
        service.version_updated_at = int(time.time())
        
        await self.db.commit()
        await self.db.refresh(service)
        
        # Log the switch
        logger.info(
            f"Service {service_id} version switched from {old_version} to {new_version} "
            f"by user {user_id} at {service.version_updated_at}"
        )
        
        return True
    
    async def get_services_using_deprecated_versions(self, model_id: str) -> List[Dict[str, Any]]:
        """
        Identify services still using deprecated versions of a model.
        Used for migration planning and notifications.
        """
        # Get all deprecated versions of the model
        stmt = select(Model).where(
            Model.model_id == model_id,
            Model.version_status == "deprecated"
        )
        result = await self.db.execute(stmt)
        deprecated_models = result.scalars().all()
        
        deprecated_versions = [m.version for m in deprecated_models]
        
        if not deprecated_versions:
            return []
        
        # Find services using these deprecated versions
        stmt = select(Service).where(
            Service.model_id == model_id,
            Service.model_version.in_(deprecated_versions)
        )
        result = await self.db.execute(stmt)
        services = result.scalars().all()
        
        result_list = []
        for service in services:
            model = await self.model_repository.find_by_model_id_and_version(
                service.model_id,
                service.model_version
            )
            result_list.append({
                "serviceId": service.service_id,
                "name": service.name,
                "endpoint": service.endpoint,
                "modelVersion": service.model_version,
                "versionStatus": model.version_status if model else "unknown"
            })
        
        return result_list

