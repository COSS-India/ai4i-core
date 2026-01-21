from typing import Dict, List, Optional
from pydantic import BaseModel , Field, field_validator
from datetime import datetime
import re


class BenchmarkEntry(BaseModel):
    output_length: int | None = None
    generated: int | None = None
    actual: int | None = None
    throughput: int | None = None

    p50: float | int | None = Field(default=None, alias="50%")
    p99: float | int |None = Field(default=None, alias="99%")

    language: str | None = None

    model_config = {
        "populate_by_name": True,
        "from_attributes": True,
    }

class ServiceStatus(BaseModel):
    status: str = None
    lastUpdated: str = None

class ServiceCreateRequest(BaseModel):
    # Note: serviceId is auto-generated as hash of (model_name, model_version, service_name)
    name: str
    serviceDescription: str
    hardwareDescription: str
    publishedOn: Optional[int] = None  # Auto-generated if not provided
    modelId: str
    modelVersion: str
    endpoint: str
    api_key: str
    healthStatus: Optional[ServiceStatus] = None
    benchmarks: Optional[Dict[str, List[BenchmarkEntry]]] = None
    isPublished: Optional[bool] = False

    @field_validator("name")
    def validate_name(cls, v):
        """Validate service name format: only alphanumeric, hyphen, and forward slash allowed."""
        if not v:
            raise ValueError("Service name is required")
        
        # Pattern: alphanumeric, hyphen, and forward slash only
        pattern = r'^[a-zA-Z0-9/-]+$'
        if not re.match(pattern, v):
            raise ValueError(
                "Service name must contain only alphanumeric characters, hyphens (-), and forward slashes (/). "
                f"Example: 'ai4bharath/indictrans-gpu'. Got: '{v}'"
            )
        return v
