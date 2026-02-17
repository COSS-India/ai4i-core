from pydantic import BaseModel
from typing import List, Optional , Dict, Any
from .model_create import InferenceEndPoint , Submitter , TaskResponse


class ModelViewRequest(BaseModel):
    modelId: str
    version: Optional[str] = None


class ModelViewRequestWithVersion(BaseModel):
    """Request body for POST /models/{model_id} - optional version for specific version lookup."""
    version: Optional[str] = None


class ModelViewResponse(BaseModel):
    modelId: str
    uuid: str
    name: str
    version: str
    versionStatus: Optional[str] = None  # Version status (ACTIVE or DEPRECATED)
    versionStatusUpdatedAt: Optional[str] = None  # Version status update timestamp
    description: str
    languages: List[Dict[str, Any]]
    domain: List[str]
    submitter: Submitter
    license: str
    inferenceEndPoint: InferenceEndPoint
    source: Optional[str]  ## ask value for this field
    task: TaskResponse  # Use TaskResponse to allow invalid task types from DB
    createdBy: Optional[str] = None  # User ID (string) who created this model
    updatedBy: Optional[str] = None  # User ID (string) who last updated this model