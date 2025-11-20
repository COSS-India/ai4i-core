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
    version: Optional[str]
    submittedOn: Optional[int]
    updatedOn: Optional[int]
    name: Optional[str]
    description: Optional[str]
    refUrl: Optional[str]
    task: Optional[Task]
    languages: Optional[List[Dict[str, Any]]]
    license: Optional[str]
    domain: Optional[List[str]]
    inferenceEndPoint: Optional[InferenceEndPoint]
    benchmarks: Optional[List[Benchmark]]
    submitter: Optional[Submitter]

    model_config = {
        "validate_by_name": True,   # replaces allow_population_by_field_name
        "from_attributes": True     # replaces orm_mode
    }
