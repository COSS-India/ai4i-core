"""
ORM → API response serializers.

Centralizes the ORM-to-API mapping so route handlers and service methods
do not duplicate this logic. Keeps the camelCase response contract used by
the deprecated model-management-service for backwards compatibility.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models.model_management.model import Model
from app.models.model_management.service import Service


def _epoch(dt: Optional[datetime]) -> Optional[int]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def model_to_dict(model: Model) -> Dict[str, Any]:
    """Serialize a Model ORM row to the API response shape."""
    return {
        "modelId": model.model_id,
        "name": model.name,
        "version": model.version,
        "submittedOn": _epoch(model.created_at),
        "versionStatus": model.version_status.value if model.version_status else None,
        "versionStatusUpdatedAt": _iso(model.version_status_updated_at),
        "description": model.description,
        "languages": model.languages or [],
        "domain": model.domain or [],
        "submitter": model.submitter,
        "license": model.license,
        "inferenceEndPoint": model.inference_endpoint,
        "source": model.ref_url or "",
        "task": model.task or {},
        "createdAt": _iso(model.created_at),
        "createdBy": model.created_by,
        "updatedBy": model.updated_by,
    }


def service_to_dict(
    service: Service,
    *,
    model: Optional[Model] = None,
    include_task_languages: bool = False,
) -> Dict[str, Any]:
    """Serialize a Service ORM row. Optionally enrich with task & languages
    from the joined Model (used by list endpoints)."""
    out: Dict[str, Any] = {
        "serviceId": service.service_id,
        "name": service.name,
        "serviceDescription": service.service_description,
        "hardwareDescription": service.hardware_description,
        "modelId": service.model_id,
        "modelVersion": service.model_version,
        "endpoint": service.endpoint,
        "inferenceServerType": service.inference_server_type or "triton",
        "sslVerify": bool(service.ssl_verify),
        "api_key": service.api_key,
        "healthStatus": service.health_status,
        "benchmarks": service.benchmarks,
        "policy": dict(service.policy) if service.policy else None,
        "isPublished": bool(service.is_published),
        "publishedAt": _iso(service.published_at),
        "unpublishedAt": _iso(service.unpublished_at),
        "createdAt": _iso(service.created_at),
        "createdBy": service.created_by,
        "updatedBy": service.updated_by,
    }
    if include_task_languages and model is not None:
        out["task"] = model.task or {"type": "unknown"}
        out["languages"] = _normalize_languages(model.languages or [])
        out["versionStatus"] = (
            model.version_status.value if model.version_status else None
        )
    return out


def _normalize_languages(raw: List[Any]) -> List[Dict[str, Any]]:
    """Coerce languages into List[Dict] form (legacy data may be List[str])."""
    out: List[Dict[str, Any]] = []
    for lang in raw:
        if isinstance(lang, dict):
            out.append(lang)
        elif isinstance(lang, str):
            out.append({"sourceLanguage": lang})
    return out


def service_detail_dict(service: Service, model: Model) -> Dict[str, Any]:
    """Full service-detail response, embedding the model card."""
    out = service_to_dict(service)
    out["model"] = model_to_dict(model) if model else None
    return out
