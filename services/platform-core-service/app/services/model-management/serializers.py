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


def _normalize_health_status(value: Any) -> Optional[Dict[str, Any]]:
    """ServiceCreateRequest writes {status, lastUpdated}, but a PATCH via
    ServiceUpdateRequest.healthStatus (Optional[str]) can persist a bare
    string into this same JSONB column. Normalize here so every response
    publishes one shape instead of exposing that write-time asymmetry as
    anyOf: [object, string] on the API contract."""
    if value is None or isinstance(value, dict):
        return value
    return {"status": str(value), "lastUpdated": None}


def _mask_api_key(key: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not key:
        return key
    return {**key, "value": "***"}


def model_to_dict(model: Model) -> Dict[str, Any]:
    """Serialize a Model ORM row to the API response shape."""
    ep = model.inference_endpoint or {}
    return {
        "modelId": model.model_id,
        "name": model.name,
        "version": model.version,
        "submittedOn": _epoch(model.created_at),
        "versionStatus": model.version_status.value if model.version_status else None,
        "versionStatusUpdatedAt": _iso(model.version_status_updated_at),
        "description": model.description,
        "languages": model.languages or [],
        "isLangDetectionEnabled": bool(model.is_lang_detection_enabled),
        "isMultilingual": bool(model.is_multilingual),
        "domain": model.domain or [],
        "submitter": model.submitter,
        "license": model.license,
        "licenseUrl": model.license_url,
        "adapterConfig": ep.get("adapterConfig") or ep.get("adapter_config"),
        "schema": ep.get("schema"),
        "callbackUrl": ep.get("callbackUrl"),
        "inferenceApiKey": _mask_api_key(ep.get("inferenceApiKey")),
        "isSyncApi": ep.get("isSyncApi"),
        "asyncApiDetails": ep.get("asyncApiDetails"),
        "source": model.ref_url or "",
        "task": model.task or {},
        "trainingDataset": model.training_dataset or None,
        "classInstance": model.class_instance,
        "createdAt": _iso(model.created_at),
        "createdBy": model.created_by,
        "updatedBy": model.updated_by,
    }


def _service_inference_api_key(service: Service) -> Optional[Dict[str, Any]]:
    """Resolve the {name, value} auth-header object for a service's
    response, masked — preferring the new structured `inference_api_key`
    column and falling back to synthesizing one from the deprecated flat
    `api_key` string so old rows still return a shape-correct object."""
    if service.inference_api_key:
        return _mask_api_key(service.inference_api_key)
    if service.api_key:
        return _mask_api_key({"name": "Authorization", "value": service.api_key})
    return None


def _service_inference_endpoint(service: Service) -> Dict[str, Any]:
    """Assemble ULCA's `inferenceEndPoint` (InferenceAPIEndPoint) object
    for a Service response from the individual mm_services columns it's
    stored across."""
    return {
        "callbackUrl": service.endpoint,
        "inferenceApiKey": _service_inference_api_key(service),
        "isMultilingualEnabled": bool(service.is_multilingual_enabled),
        "supportedInputFormats": service.supported_input_formats,
        "supportedOutputFormats": service.supported_output_formats,
        "schema": service.inference_schema,
        "isSyncApi": service.is_sync_api,
        "asyncApiDetails": service.async_api_details,
        "providerName": service.provider_name,
        "infraDescription": service.hardware_description,
        "inferenceModelId": service.inference_model_id,
    }


def service_to_dict(
    service: Service,
    *,
    model: Optional[Model] = None,
    include_task_languages: bool = False,
    tier_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Serialize a Service ORM row. Optionally enrich with languages &
    versionStatus from the joined Model (used by list endpoints)."""
    out: Dict[str, Any] = {
        "serviceId": service.service_id,
        "name": service.name,
        "description": service.service_description,
        "serviceDescription": service.service_description,
        "hardwareDescription": service.hardware_description,
        "modelId": service.model_id,
        "modelVersion": service.model_version,
        # task_type is denormalized onto Service for billing/filtering, but
        # the ULCA-shaped `task` object is sourced from the joined Model
        # when available (task type is conceptually a model-card fact) and
        # falls back to the denormalized column otherwise.
        "task": (model.task if model and model.task else {"type": service.task_type})
                if service.task_type or (model and model.task) else None,
        "taskType": service.task_type,
        "inferenceEndPoint": _service_inference_endpoint(service),
        "endpoint": service.endpoint,
        "inferenceServerType": service.inference_server_type or "triton",
        "sslVerify": bool(service.ssl_verify),
        # Deprecated — use `inferenceEndPoint.inferenceApiKey` (masked, see
        # _service_inference_api_key). This flat field is deliberately left
        # UNMASKED, unlike Model's equivalent field: inference-service reads
        # this exact key off this exact response
        # (services/inference-service/services/base/task_service.py) to
        # build the outbound `Authorization: Bearer` header for the real
        # Triton call — masking it here breaks every auth-protected Triton
        # backend platform-wide (see test_triton_url_redaction.py for the
        # regression test guarding this).
        "api_key": service.api_key,
        "healthStatus": _normalize_health_status(service.health_status),
        "benchmarks": service.benchmarks,
        "expectedResponseSchema": service.expected_response_schema,
        "isPublished": bool(service.is_published),
        "isTryItDefault": bool(service.is_try_it_default),
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


def service_detail_dict(
    service: Service,
    model: Model,
    tier_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Full service-detail response, embedding the model card."""
    out = service_to_dict(service, model=model, tier_names=tier_names)
    out["model"] = model_to_dict(model) if model else None
    return out
