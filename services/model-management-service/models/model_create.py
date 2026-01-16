from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel , field_validator, ConfigDict
from models.type_enum import TaskTypeEnum
from models.db_models import VersionStatus

class ModelProcessingType(BaseModel):
    type: str


class Schema(BaseModel):
    modelProcessingType: ModelProcessingType
    model_name: Optional[str] = None
    request: Dict[str, Any] = {}
    response: Dict[str, Any] = {}


class InferenceEndPoint(BaseModel):
    schema: Schema
    endpoint: Optional[str] = None
    model_name: Optional[str] = None
    modelName: Optional[str] = None  # Alternative field name
    model: Optional[str] = None  # Alternative field name
    
    model_config = ConfigDict(extra="allow")  # Allow extra fields that aren't defined


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
    type: TaskTypeEnum
    
    @field_validator("type", mode="before")
    def normalize_and_validate_task_type(cls, v):
        if not v:
            return v
        
        if isinstance(v, str):
            v_normalized = v.lower()
            for enum_member in TaskTypeEnum:
                if enum_member.value.lower() == v_normalized:
                    return enum_member.value
        
            valid_types = [e.value for e in TaskTypeEnum]
            raise ValueError(
                f"Invalid task type '{v}'. Valid types are: {', '.join(valid_types)}"
            )
        
        if isinstance(v, TaskTypeEnum):
            return v.value

        return v


class ModelCreateRequest(BaseModel):
    modelId: str
    version: str
    versionStatus: Optional[VersionStatus] = VersionStatus.ACTIVE  
    submittedOn: Optional[int] = None 
    updatedOn: Optional[int] = None 
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

    model_config = {
        "validate_by_name": True,  
        "from_attributes": True 
    }
