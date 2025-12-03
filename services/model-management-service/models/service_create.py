from typing import Dict, List, Optional
from pydantic import BaseModel
from datetime import datetime


class BenchmarkEntry(BaseModel):
    output_length: int
    generated: int
    actual: int
    throughput: int
    _50: int
    _99: int
    language: str

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
