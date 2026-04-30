from pydantic import BaseModel, field_validator
from typing import Optional, Dict, List

from .service_create import ServiceStatus, BenchmarkEntry
from models.inference_server_type import InferenceServerType

_INFERENCE_SERVER_VALUES = {e.value for e in InferenceServerType}


class LanguagePair(BaseModel):
    sourceLanguage: Optional[str]
    sourceScriptCode: Optional[str] = ""
    targetLanguage: str
    targetScriptCode: Optional[str] = ""


class ServiceUpdateRequest(BaseModel):
    # Note: serviceId is used only for identifying the service to update
    # Note: name, modelId, and modelVersion are NOT updatable since service_id is derived from service name only
    serviceId: str
    serviceDescription: Optional[str] = None
    hardwareDescription: Optional[str] = None
    publishedOn: Optional[int] = None
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    inferenceServerType: Optional[str] = None
    sslVerify: Optional[bool] = None
    languagePair: Optional[LanguagePair] = None
    healthStatus: Optional[ServiceStatus] = None
    benchmarks: Optional[Dict[str, List[BenchmarkEntry]]] = None
    isPublished: Optional[bool] = None

    @field_validator("inferenceServerType", mode="before")
    @classmethod
    def validate_inference_server_type_optional(cls, v):
        if v is None:
            return None
        s = str(v).strip().lower()
        if s not in _INFERENCE_SERVER_VALUES:
            raise ValueError(
                f"inferenceServerType must be one of {sorted(_INFERENCE_SERVER_VALUES)}, got {v!r}"
            )
        return s

