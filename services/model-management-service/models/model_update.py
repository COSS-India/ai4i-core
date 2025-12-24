from typing import List, Optional , Dict, Any
from pydantic import BaseModel
from .model_create import (
    Benchmark,
    InferenceEndPoint,
    Submitter,
    Task,
)

class ModelUpdateRequest(BaseModel):
    modelId: str
    version: Optional[str] = None  # Version cannot be changed once created, but needed for identifying which version to update
    submittedOn: Optional[int] = None
    updatedOn: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    refUrl: Optional[str] = None
    task: Optional[Task] = None
    languages: Optional[List[Dict[str, Any]]] = None
    license: Optional[str] = None
    domain: Optional[List[str]] = None
    inferenceEndPoint: Optional[InferenceEndPoint] = None
    benchmarks: Optional[List[Benchmark]] = None
    submitter: Optional[Submitter] = None
    releaseNotes: Optional[str] = None

    model_config = {
        "validate_by_name": True,   # replaces allow_population_by_field_name
        "from_attributes": True     # replaces orm_mode
    }
