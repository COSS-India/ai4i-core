from pydantic import BaseModel
from pydantic import BaseModel
from typing import List, Optional , Dict, Any
from .model_create import InferenceEndPoint , Submitter , Task


class ModelViewRequest(BaseModel):
    modelId: str


class ModelViewResponse(BaseModel):
    modelId: str
    uuid: str
    version: str
    name: str
    description: str
    languages: List[Dict[str, Any]]
    domain: List[str]
    submitter: Submitter
    license: str
    inferenceEndPoint: InferenceEndPoint
    source: Optional[str]  ## ask value for this field
    task: Task
    isPublished: bool
    publishedAt: Optional[str]
    unpublishedAt: Optional[str]
    versionStatus: str
    releaseNotes: Optional[str] = None
    isImmutable: bool
    allVersions: Optional[List[str]] = None
