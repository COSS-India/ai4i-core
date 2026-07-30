"""
Model management API endpoints.
"""

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.exceptions import ValidationError
from app.core.responses import success_response
from app.dependencies.services import ModelService, get_model_service
from app.schemas.enums.model_management import TaskTypeEnum, VersionStatusEnum
from app.schemas.model_management.model import (
    ModelCreateRequest,
    ModelUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/models",
    tags=["Model Management"],
)


def _resolve_task_type(task_type: Optional[str]) -> Optional[str]:
    """Translate the raw query-string into a normalized task-type value.

    `None` and the literal string `"none"` (case-insensitive) both mean
    "no filter".
    """
    if not task_type or task_type.lower() == "none":
        return None
    try:
        return TaskTypeEnum(task_type).value
    except ValueError:
        valid = [e.value for e in TaskTypeEnum]
        raise ValidationError(f"Invalid task_type '{task_type}'. Must be one of: {valid}")


_MODEL_ID_RE = re.compile(r"^(?=.*[a-zA-Z0-9])[a-zA-Z0-9/_-]+$")
_MODEL_ID_MAX_LEN = 255


def _validate_model_id(model_id: str) -> str:
    """Reject a structurally invalid model_id before any DB lookup is attempted
    (AI4IDS-1932) — mirrors ServiceCreateRequest._validate_service_id's format
    (schemas/model_management/service.py), since model_id and serviceId are the
    same class of opaque identifier in this codebase.
    """
    if not model_id or not model_id.strip():
        raise ValidationError("model_id must not be empty")
    if len(model_id) > _MODEL_ID_MAX_LEN:
        raise ValidationError(f"model_id must not exceed {_MODEL_ID_MAX_LEN} characters")
    if not _MODEL_ID_RE.match(model_id):
        raise ValidationError(
            "model_id must contain only alphanumeric characters, /, -, or _ "
            "and include at least one alphanumeric character"
        )
    return model_id


@router.get("")
async def list_models(
    response: Response,
    task_type: Optional[str] = Query(
        None,
        description="Filter by a single task type (asr, nmt, tts, etc.).",
    ),
    task_types: Optional[str] = Query(
        None,
        description="Comma-separated task types to include (frontend allowlist).",
    ),
    include_deprecated: bool = Query(
        True,
        description="Include deprecated versions.",
    ),
    version_status: Optional[str] = Query(
        None,
        description="Filter by version status: 'active' or 'deprecated'. Overrides include_deprecated.",
    ),
    model_name: Optional[str] = Query(
        None,
        description="Filter by exact model name (returns all versions).",
    ),
    created_by: Optional[str] = Query(
        None,
        description="Filter by user ID who created the model.",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Number of items to skip (for pagination).",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Maximum number of items to return. Defaults to 100.",
    ),
    svc: ModelService = Depends(get_model_service),
):
    """List models with optional filters and offset/limit pagination."""
    valid_version_statuses = [e.value.lower() for e in VersionStatusEnum]
    if version_status is not None and version_status not in valid_version_statuses:
        raise ValidationError(f"Invalid version_status. Accepted values are: {valid_version_statuses}.")
    # Merge the single task_type= (backward-compat, strictly validated) and the
    # task_types= allowlist into one list — the service/repo take a single
    # task_types filter. The allowlist is parsed leniently: names outside
    # TaskTypeEnum (e.g. catalog entries with no registered models) are skipped
    # rather than failing the whole request — they can't match any row anyway.
    _task_types = []
    if task_types:
        valid = {m.value for m in TaskTypeEnum}
        _task_types = [t.strip().lower() for t in task_types.split(",") if t.strip().lower() in valid]
    _single = _resolve_task_type(task_type)
    if _single:
        _task_types.insert(0, _single)
    items, total = await svc.list_models(
        task_types=_task_types or None,
        include_deprecated=include_deprecated,
        version_status=version_status,
        model_name=model_name,
        created_by=created_by,
        offset=offset,
        limit=limit,
    )
    response.headers["X-Total-Count"] = str(total)
    return success_response(
        data=items,
        meta={"total": total, "offset": offset, "limit": limit},
    )


@router.get("/{model_id:path}", summary="Retrieve Model")
async def get_model_by_id(
    model_id: str,
    version: Optional[str] = Query(None, description="Specific model version. If omitted, returns the latest active version."),
    svc: ModelService = Depends(get_model_service),
):
    """Retrieve a model by ID."""
    model_id = _validate_model_id(model_id)
    data = await svc.get_model(model_id, version=version)
    return success_response(data=data)


@router.post(
    "",
    status_code=201,
    summary="Register a new model version (ULCA model-schema conformant)",
    description=(
        "Registers a new model version in the registry. The request body "
        "follows ULCA's `model-schema.yml` Model object: `name`, `version`, "
        "`description`, `task`, `license`, `domain`, `submitter`, "
        "`inferenceEndPoint`, and `trainingDataset` are required; "
        "`refUrl`, `languages`, `isLangDetectionEnabled`, `isMultilingual`, "
        "`licenseUrl`, `benchmarks`, and `classInstance` are optional (see "
        "each field's description in the schema below for its default, if "
        "any). Use the 'Example Value' tab for a full worked payload."
    ),
)
async def create_model(
    request: Request,
    payload: ModelCreateRequest,
    svc: ModelService = Depends(get_model_service),
):
    """Create a new model version."""
    user_id = request.headers.get("X-User-Id")
    model_id = await svc.create_model(payload, created_by=user_id)
    return success_response(
        data={
            "modelId": model_id,
            "name": payload.name,
            "version": payload.version,
        },
        meta={"message": f"Model '{payload.name}' created successfully."},
    )


@router.patch(
    "",
    summary="Partially update a model version (ULCA model-schema conformant)",
    description=(
        "Applies a partial update to an existing (modelId, version). Only "
        "`modelId` and `version` are required — every other ULCA Model "
        "field (`description`, `task`, `languages`, `license`, `domain`, "
        "`submitter`, `inferenceEndPoint`, `trainingDataset`, etc.) is "
        "optional; omit a field to leave it unchanged. `name` cannot be "
        "changed (modelId is derived from name+version — create a new "
        "version instead). `inferenceEndPoint` merges: send only the keys "
        "you want changed (e.g. just `adapterConfig`), no need to resend "
        "`callbackUrl`/`schema`. Never resend a GET response's "
        "`inferenceApiKey.value` verbatim — it comes back as '[REDACTED]' "
        "and that sentinel is stripped before merge, so it won't corrupt "
        "the stored secret, but it also won't update it. Use the 'Example "
        "Value' tab for a realistic partial-update payload."
    ),
)
async def update_model(
    request: Request,
    payload: ModelUpdateRequest,
    svc: ModelService = Depends(get_model_service),
):
    """Update an existing model version."""
    user_id = request.headers.get("X-User-Id")
    await svc.update_model(payload, updated_by=user_id)
    return success_response(
        data={"modelId": payload.modelId, "version": payload.version},
        meta={"message": f"Model '{payload.modelId}' updated successfully."},
    )


@router.delete("/{model_id:path}")
async def delete_model(
    model_id: str,
    svc: ModelService = Depends(get_model_service),
):
    """Delete a model by its hash-generated model ID."""
    await svc.delete_model(model_id)
    return success_response(
        data={"modelId": model_id},
        meta={"message": f"Model '{model_id}' deleted successfully."},
    )
