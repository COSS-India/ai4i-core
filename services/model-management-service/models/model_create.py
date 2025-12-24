from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel , field_validator
from models.type_enum import TaskTypeEnum
from datetime import datetime

class ModelProcessingType(BaseModel):
    type: str


class Schema(BaseModel):
    modelProcessingType: ModelProcessingType
    request: Dict[str, Any] = {}
    response: Dict[str, Any] = {}


class InferenceEndPoint(BaseModel):
    schema: Schema


class Score(BaseModel):
    metricName: str
    score: str


class BenchmarkLanguage(BaseModel):
    sourceLanguage: Optional[str]
    targetLanguage: Optional[str]


class Benchmark(BaseModel):
    benchmarkId: str
    name: str
    description: str
    domain: str
    createdOn: datetime
    languages: BenchmarkLanguage
    score: List[Score]


class OAuthId(BaseModel):
    oauthId: str
    provider: str


class TeamMember(BaseModel):
    name: str
    aboutMe: Optional[str]
    oauthId: Optional[OAuthId]


class Submitter(BaseModel):
    name: str
    aboutMe: Optional[str]
    team: List[TeamMember]


class Task(BaseModel):
    type: str


class ModelCreateRequest(BaseModel):
    modelId: str
    version: str
    submittedOn: int
    updatedOn: int = None
    name: str
    description: str
    refUrl: str
    task: Task
    languages: List[Dict[str, Any]]
    license: str
    domain: List[str]
    inferenceEndPoint: InferenceEndPoint
    benchmarks: List[Benchmark]
    submitter: Submitter
    releaseNotes: Optional[str] = None
    versionStatus: str = "active"

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
