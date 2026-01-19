from pydantic import BaseModel, field_validator
from typing import Optional , Dict , List
import re

from .service_create import ServiceStatus, BenchmarkEntry


class LanguagePair(BaseModel):
    sourceLanguage: Optional[str]
    sourceScriptCode: Optional[str] = ""
    targetLanguage: str
    targetScriptCode: Optional[str] = ""


class ServiceUpdateRequest(BaseModel):
    serviceId: str
    name: Optional[str] = None
    serviceDescription: Optional[str] = None
    hardwareDescription: Optional[str] = None
    publishedOn: Optional[int] = None
    modelId: Optional[str] = None
    modelVersion: Optional[str] = None  
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    languagePair: Optional[LanguagePair] = None
    healthStatus: Optional[ServiceStatus] = None
    benchmarks: Optional[Dict[str, List[BenchmarkEntry]]] = None
    isPublished: Optional[bool] = None

    @field_validator("name")
    def validate_name(cls, v):
        """Validate service name format: only alphanumeric, hyphen, and forward slash allowed."""
        # Allow None for optional field in updates
        if v is None:
            return v
        
        # Pattern: alphanumeric, hyphen, and forward slash only
        pattern = r'^[a-zA-Z0-9/-]+$'
        if not re.match(pattern, v):
            raise ValueError(
                "Service name must contain only alphanumeric characters, hyphens (-), and forward slashes (/). "
                f"Example: 'ai4bharath/indictrans-gpu'. Got: '{v}'"
            )
        return v
    

