from typing import List, Optional
from pydantic import BaseModel, field_validator
from enum import Enum


class VersionStatusEnum(str, Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class ModelVersionCreateRequest(BaseModel):
    """Request model for creating a new version under an existing model"""
    version: str
    releaseNotes: Optional[str] = None
    versionStatus: str = "active"
    
    @field_validator("version")
    def validate_version_format(cls, v):
        """Validate version follows semantic versioning pattern (e.g., 1.0.0)"""
        import re
        if not re.match(r'^\d+\.\d+\.\d+', v):
            raise ValueError(f"Version must follow semantic versioning pattern (e.g., '1.0.0'), got: {v}")
        return v
    
    @field_validator("versionStatus")
    def validate_version_status(cls, v):
        """Validate version status is either 'active' or 'deprecated'"""
        if v not in ["active", "deprecated"]:
            raise ValueError(f"versionStatus must be 'active' or 'deprecated', got: {v}")
        return v


class ModelVersionListResponse(BaseModel):
    """Response model for listing all versions of a model"""
    modelId: str
    versions: List[dict]  # List of version details with metadata


class ModelVersionStatusUpdateRequest(BaseModel):
    """Request model for updating version status (e.g., deprecating a version)"""
    modelId: str
    version: str
    versionStatus: str  # "active" or "deprecated"
    
    @field_validator("versionStatus")
    def validate_version_status(cls, v):
        """Validate version status is either 'active' or 'deprecated'"""
        if v not in ["active", "deprecated"]:
            raise ValueError(f"versionStatus must be 'active' or 'deprecated', got: {v}")
        return v

