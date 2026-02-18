from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel , field_validator, ConfigDict
import re
from models.type_enum import TaskTypeEnum, LicenseEnum
from models.db_models import VersionStatus

class ModelProcessingType(BaseModel):
    type: str


class Schema(BaseModel):
    modelProcessingType: Optional[ModelProcessingType] = None
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
    aboutMe: Optional[str] = None
    oauthId: Optional[OAuthId] = None
    
    model_config = ConfigDict(extra="ignore")  # Ignore extra fields like 'role'


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


class TaskResponse(BaseModel):
    """Task model with lenient validation - allows invalid types from DB for responses."""
    type: str  # Allow any string value to handle invalid task types in DB
    
    @field_validator("type", mode="before")
    def normalize_task_type(cls, v):
        if not v:
            return v
        
        if isinstance(v, str):
            v_normalized = v.lower()
            # Try to normalize to valid enum value if it matches
            for enum_member in TaskTypeEnum:
                if enum_member.value.lower() == v_normalized:
                    return enum_member.value
            # If no match found, return the original string value (allow invalid types)
            return v
        
        if isinstance(v, TaskTypeEnum):
            return v.value

        return v


class ModelCreateRequest(BaseModel):
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

    @field_validator("name")
    def validate_name(cls, v):
        """Validate model name format: only alphanumeric, hyphen, and forward slash allowed."""
        if not v:
            raise ValueError("Model name is required")
        
        # Pattern: alphanumeric, hyphen, and forward slash only
        pattern = r'^[a-zA-Z0-9/-]+$'
        if not re.match(pattern, v):
            raise ValueError(
                "Model name must contain only alphanumeric characters, hyphens (-), and forward slashes (/). "
                f"Example: 'ai4bharath/indictrans-gpu'. Got: '{v}'"
            )
        return v

    @field_validator("license", mode="before")
    def validate_license(cls, v):
        if not v:
            raise ValueError("License field is required")
        
        if isinstance(v, str):
            v_normalized = v.strip()
            # Check if the license matches any enum value (case-insensitive)
            for enum_member in LicenseEnum:
                if enum_member.value.lower() == v_normalized.lower():
                    return enum_member.value
            
            # If no match found, raise error with valid options
            valid_licenses = [e.value for e in LicenseEnum]
            raise ValueError(
                f"Invalid license '{v}'. Valid licenses are: {', '.join(valid_licenses)}"
            )
        
        if isinstance(v, LicenseEnum):
            return v.value
        
        return v

    model_config = {
        "validate_by_name": True,  
        "from_attributes": True 
    }
