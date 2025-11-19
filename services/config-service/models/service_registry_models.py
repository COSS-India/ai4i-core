from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ServiceStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    STARTING = "starting"
    STOPPING = "stopping"


class ServiceRegistration(BaseModel):
    service_name: str = Field(..., description="Service name")
    service_url: str = Field(..., description="Base URL of the service")
    health_check_url: Optional[str] = Field(None, description="Health check endpoint URL")
    service_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


class ServiceUpdate(BaseModel):
    status: Optional[ServiceStatus] = Field(None, description="Updated status")
    service_metadata: Optional[Dict[str, Any]] = Field(None, description="Updated metadata")


class ServiceQuery(BaseModel):
    service_name: Optional[str] = None
    status: Optional[ServiceStatus] = None


class ServiceInstance(BaseModel):
    instance_id: Optional[str] = None
    service_name: str
    service_url: str
    health_check_url: Optional[str] = None
    status: ServiceStatus = ServiceStatus.UNKNOWN
    service_metadata: Dict[str, Any] = Field(default_factory=dict)
    registered_at: Optional[str] = None
    last_health_check: Optional[str] = None


class ServiceListResponse(BaseModel):
    items: List[ServiceInstance]
    total: int


class ServiceHealthResponse(BaseModel):
    service_name: str
    status: ServiceStatus
    last_check: Optional[str]
    response_time_ms: Optional[float]


