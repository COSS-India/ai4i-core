from typing import List, Optional , Dict, Any
from pydantic import BaseModel, field_validator
from .model_create import (
    Benchmark,
    InferenceEndPoint,
    Submitter,
    Task,
)
from .db_models import VersionStatus
from .type_enum import LicenseEnum

class ModelUpdateRequest(BaseModel):
    modelId: str
    version: Optional[str] = None  
    versionStatus: Optional[VersionStatus] = None  
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

    @field_validator("license", mode="before")
    def validate_license(cls, v):
        # Allow None for optional field in updates
        if v is None:
            return v
        
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
        "validate_by_name": True,   # replaces allow_population_by_field_name
        "from_attributes": True     # replaces orm_mode
    }
