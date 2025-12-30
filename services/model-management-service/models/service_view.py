from pydantic import BaseModel , field_validator
from typing import Dict, List, Optional
from .service_create import ServiceStatus, BenchmarkEntry
from .model_create import ModelCreateRequest
from datetime import datetime

class ServiceViewRequest(BaseModel):
    serviceId: str

class ServiceResponse(BaseModel):
    serviceId: str
    uuid: str
    name: str
    serviceDescription: str
    hardwareDescription: str
    publishedOn: int
    modelId: str
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    healthStatus: Optional[ServiceStatus] = None
    benchmarks: Optional[Dict[str, List[BenchmarkEntry]]] = None


class _ServiceUsage(BaseModel):
    service_id: str
    usage: int

class BaseApiKey(BaseModel):
    name: str


class ApiKey(BaseApiKey):
    masked_key: str
    active: bool
    type: str
    created_timestamp: datetime
    services: List[_ServiceUsage]
    data_tracking: bool


class _ApiKey(ApiKey):
    id: str

    @field_validator("id", mode="before")
    def typecast_id_to_str(cls, v):
        return str(v)

class ServiceViewResponse(ServiceResponse):
    model: ModelCreateRequest
    key_usage: List[_ApiKey] = []
    total_usage: int = 0