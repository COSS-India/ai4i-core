from typing import Dict, List, Optional
from pydantic import BaseModel , Field
from datetime import datetime


class BenchmarkEntry(BaseModel):
    output_length: int | None = None
    generated: int | None = None
    actual: int | None = None
    throughput: int | None = None

    p50: int | None = Field(default=None, alias="50%")
    p99: int | None = Field(default=None, alias="99%")

    language: str | None = None

    model_config = {
        "populate_by_name": True,
        "from_attributes": True,
    }

class ServiceStatus(BaseModel):
    status: str = None
    lastUpdated: str = None

class ServiceCreateRequest(BaseModel):
    serviceId: str
    name: str
    serviceDescription: str
    hardwareDescription: str
    publishedOn: int
    modelId: str
    endpoint: str
    api_key: str
    healthStatus: Optional[ServiceStatus] = None
    benchmarks: Optional[Dict[str, List[BenchmarkEntry]]] = None
