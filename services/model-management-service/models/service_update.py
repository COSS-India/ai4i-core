from pydantic import BaseModel
from typing import Optional , Dict , List

from .service_create import ServiceStatus, BenchmarkEntry


class LanguagePair(BaseModel):
    sourceLanguage: Optional[str]
    sourceScriptCode: Optional[str] = ""
    targetLanguage: str
    targetScriptCode: Optional[str] = ""


class ServiceUpdateRequest(BaseModel):
    serviceId: str
    name: str
    serviceDescription: Optional[str] = None
    hardwareDescription: Optional[str] = None
    publishedOn: Optional[int] = None
    modelId: str
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    languagePair: Optional[LanguagePair] = None
    healthStatus: Optional[ServiceStatus] = None
    benchmarks: Optional[Dict[str, List[BenchmarkEntry]]] = None
    

