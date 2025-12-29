from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel , field_validator
from models.type_enum import TaskTypeEnum
from datetime import datetime

class ModelProcessingType(BaseModel):
    type: Optional[str] = None


class Schema(BaseModel):
    modelProcessingType: Optional[ModelProcessingType] = None
    request: Optional[Dict[str, Any]] = None
    response: Optional[Dict[str, Any]] = None


class InferenceEndPoint(BaseModel):
    schema_: Optional[Schema] = None  # Renamed to avoid shadowing BaseModel.schema
    modelName: Optional[str] = None
    format: Optional[str] = None
    
    class Config:
        fields = {'schema_': 'schema'}  # Map schema_ to schema in JSON


class Score(BaseModel):
    metricName: str
    score: str


class BenchmarkLanguage(BaseModel):
    sourceLanguage: Optional[str]
    targetLanguage: Optional[str]


class Benchmark(BaseModel):
    benchmarkId: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    domain: Optional[str] = None
    createdOn: Optional[datetime] = None
    languages: Optional[BenchmarkLanguage] = None
    score: Optional[List[Score]] = None


class OAuthId(BaseModel):
    oauthId: str
    provider: str


class TeamMember(BaseModel):
    name: str
    aboutMe: Optional[str]
    oauthId: Optional[OAuthId]


class Submitter(BaseModel):
    name: str
    aboutMe: Optional[str] = None
    team: Optional[List[TeamMember]] = None
    organization: Optional[str] = None
    contact: Optional[str] = None


class Task(BaseModel):
    type: str


class ModelCreateRequest(BaseModel):
    modelId: str
    version: str
    submittedOn: Optional[int] = None
    updatedOn: Optional[int] = None
    name: str
    description: Optional[str] = None
    refUrl: Optional[str] = None
    task: Task
    languages: Optional[List[Dict[str, Any]]] = None
    license: Optional[str] = None
    domain: Optional[List[str]] = None
    inferenceEndPoint: Optional[InferenceEndPoint] = None
    benchmarks: Optional[List[Benchmark]] = None
    submitter: Optional[Submitter] = None

    model_config = {
        "validate_by_name": True,   # replaces allow_population_by_field_name
        "from_attributes": True     # replaces orm_mode
    }

    @field_validator("task", mode="before")
    def normalize_and_validate_task(cls, v):
        if not v:
            return v
    
        if "type" in v and isinstance(v["type"], str):
            v["type"] = v["type"].lower()
    
        valid_types = [e.value for e in TaskTypeEnum]
    
        if v["type"] not in valid_types:
            raise ValueError(
                f"Invalid task type '{v['type']}'. Valid types are: {', '.join(valid_types)}"
            )
    
        return v
