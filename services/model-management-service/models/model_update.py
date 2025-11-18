from typing import List, Optional
from pydantic import BaseModel
from .model_create import (
    Benchmark,
    InferenceEndPoint,
    Submitter,
    Task,
)

class ModelUpdateRequest(BaseModel):
    modelId: str
    name: Optional[str]
    description: Optional[str]
    refUrl: Optional[str]
    task: Optional[Task]
    languages: Optional[List[dict]]
    license: Optional[str]
    domain: Optional[List[str]]
    inferenceEndPoint: Optional[InferenceEndPoint]
    benchmarks: Optional[List[Benchmark]]
    submitter: Optional[Submitter]