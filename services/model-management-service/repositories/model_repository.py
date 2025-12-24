"""
Repository layer for Model operations with version support.
Follows existing repository pattern in the codebase.
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
from models.db_models import Model
from logger import logger


class ModelRepository:
    """Repository for model database operations with version support."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def find_by_model_id_and_version(self, model_id: str, version: str) -> Optional[Model]:
        """Fetch a specific model version by model_id and version."""
        try:
            stmt = select(Model).where(
                Model.model_id == model_id,
                Model.version == version
            )
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error finding model {model_id} version {version}: {e}")
            raise
    
    async def find_all_versions(self, model_id: str) -> List[Model]:
        """Retrieve all versions of a model."""
        try:
            stmt = select(Model).where(Model.model_id == model_id).order_by(Model.version.desc())
            result = await self.db.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error finding all versions for model {model_id}: {e}")
            raise
    
    async def find_active_versions(self, model_id: str) -> List[Model]:
        """Get only active versions of a model."""
        try:
            stmt = select(Model).where(
                Model.model_id == model_id,
                Model.version_status == "active"
            ).order_by(Model.version.desc())
            result = await self.db.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error finding active versions for model {model_id}: {e}")
            raise
    
    async def count_active_versions(self, model_id: str) -> int:
        """Count active versions for a model."""
        try:
            stmt = select(func.count(Model.id)).where(
                Model.model_id == model_id,
                Model.version_status == "active"
            )
            result = await self.db.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error counting active versions for model {model_id}: {e}")
            raise
    
    async def mark_version_as_deprecated(self, model_id: str, version: str) -> bool:
        """Mark a specific version as deprecated."""
        try:
            model = await self.find_by_model_id_and_version(model_id, version)
            if not model:
                return False
            
            model.version_status = "deprecated"
            await self.db.commit()
            await self.db.refresh(model)
            logger.info(f"Model {model_id} version {version} marked as deprecated")
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deprecating model {model_id} version {version}: {e}")
            raise
    
    async def mark_version_as_immutable(self, model_id: str, version: str) -> bool:
        """Mark a version as immutable to prevent modifications."""
        try:
            model = await self.find_by_model_id_and_version(model_id, version)
            if not model:
                return False
            
            model.is_immutable = True
            await self.db.commit()
            await self.db.refresh(model)
            logger.info(f"Model {model_id} version {version} marked as immutable")
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error marking model {model_id} version {version} as immutable: {e}")
            raise
    
    async def check_version_exists(self, model_id: str, version: str) -> bool:
        """Check if a specific version already exists for a model."""
        try:
            model = await self.find_by_model_id_and_version(model_id, version)
            return model is not None
        except Exception as e:
            logger.error(f"Error checking version existence for {model_id} version {version}: {e}")
            raise
    
    async def find_by_model_id(self, model_id: str) -> Optional[Model]:
        """Find a model by model_id (returns first match, typically latest version)."""
        try:
            stmt = select(Model).where(Model.model_id == model_id).order_by(Model.version.desc()).limit(1)
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error finding model {model_id}: {e}")
            raise
    
    async def get_latest_active_version(self, model_id: str) -> Optional[Model]:
        """Get the latest active version of a model."""
        try:
            stmt = select(Model).where(
                Model.model_id == model_id,
                Model.version_status == "active"
            ).order_by(Model.version.desc()).limit(1)
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error finding latest active version for model {model_id}: {e}")
            raise

