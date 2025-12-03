from typing import Dict, List, Optional
from pydantic import BaseModel
from datetime import datetime


class BenchmarkEntry(BaseModel):
    output_length: int = None
    generated: int = None
    actual: int = None
    throughput: int = None
    _50: int = None
    _99: int = None
    language: str = None

    model_config = {
        "populate_by_name": True,
        "fields": {
            "_50": "50%",
            "_99": "99%",
        },
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
