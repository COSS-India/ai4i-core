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
        "source": model.ref_url or "",
        "task": model.task or {},
        "classInstance": model.class_instance,
        "createdAt": _iso(model.created_at),
        "createdBy": model.created_by,
        "updatedBy": model.updated_by,
    }


def service_to_dict(
    service: Service,
    *,
    model: Optional[Model] = None,
    include_task_languages: bool = False,
    tier_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Serialize a Service ORM row. Optionally enrich with the linked model's
    lifecycle status (used by list endpoints)."""
    out: Dict[str, Any] = {
        "serviceId": service.service_id,
        "name": service.name,
        "version": service.version,
        "description": service.service_description,
        "refUrl": service.ref_url,
        "task": service.task or {"type": "unknown"},
        "languages": _normalize_languages(service.languages or []),
        "license": service.license,
        "domain": service.domain or [],
        "submitter": service.submitter,
        "trainingDataset": service.training_dataset,
        "inferenceEndPoint": service.inference_endpoint,
        "hardwareDescription": service.hardware_description,
        "modelId": service.model_id,
        "modelVersion": service.model_version,
        "inferenceServerType": service.inference_server_type or "triton",
        "sslVerify": bool(service.ssl_verify),
        "healthStatus": service.health_status,
        "benchmarks": service.benchmarks,
        "policy": dict(service.policy) if service.policy else None,
        "isPublished": bool(service.is_published),
        "publishedAt": _iso(service.published_at),
        "unpublishedAt": _iso(service.unpublished_at),
        "costPerUnit": float(service.cost_per_unit) if service.cost_per_unit is not None else None,
        "unitSize": service.unit_size,
        "unitRate": float(service.unit_rate) if service.unit_rate is not None else None,
        "tierIds": service.tier_ids,
        "tierNames": tier_names,
        "deletedAt": _iso(service.deleted_at),
        "createdAt": _iso(service.created_at),
        "createdBy": service.created_by,
        "updatedBy": service.updated_by,
    }
    if include_task_languages and model is not None:
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


def service_detail_dict(
    service: Service,
    model: Model,
    tier_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Full service-detail response, embedding the model card."""
    out = service_to_dict(service, tier_names=tier_names)
    out["model"] = model_to_dict(model) if model else None
    return out
