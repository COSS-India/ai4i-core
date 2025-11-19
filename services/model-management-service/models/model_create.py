from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
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
    updatedOn: int
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
        "validate_by_name": True,   # replaces allow_population_by_field_name
        "from_attributes": True     # replaces orm_mode
    }

