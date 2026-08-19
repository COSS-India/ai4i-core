"""
Model management API endpoints.
"""

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.exceptions import ValidationError
from app.dependencies.services import ModelService, get_model_service
from app.schemas.common import MessageMeta, error_responses
from app.schemas.enums.model_management import TaskTypeEnum, VersionStatusEnum
from app.schemas.model_management.model import (
    CreateModelData,
    CreateModelResponse,
    DeleteModelData,
    DeleteModelResponse,
    GetModelResponse,
    ListModelsResponse,
    ModelCreateRequest,
    ModelListMeta,
    ModelUpdateRequest,
    UpdateModelData,
    UpdateModelResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/models",
    tags=["Model Management"],
)


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
    task_types: Optional[str] = Query(
        None,
        description="Comma-separated task types to include. A single value is a one-element list.",
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
) -> ListModelsResponse:
    """List models with optional filters and offset/limit pagination."""
    valid_version_statuses = [e.value.lower() for e in VersionStatusEnum]
    if version_status is not None and version_status not in valid_version_statuses:
        raise ValidationError(f"Invalid version_status. Accepted values are: {valid_version_statuses}.")
    # ONE task-type filter param: a drill-down is just a one-element list, so a
    # separate single param would only recreate union/precedence ambiguity.
    # Parsed leniently: names outside TaskTypeEnum (e.g. catalog entries with no
    # registered models) are skipped rather than failing the whole request —
    # they can't match any row anyway.
    _task_types = []
    if task_types:
        valid = {m.value for m in TaskTypeEnum}
        _task_types = [t.strip().lower() for t in task_types.split(",") if t.strip().lower() in valid]
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
    return ListModelsResponse(
        success=True,
        data=items,
        meta=ModelListMeta(total=total, offset=offset, limit=limit),
    )


@router.get("/{model_id:path}", summary="Retrieve Model", responses=error_responses(404))
async def get_model_by_id(
    model_id: str,
    version: Optional[str] = Query(None, description="Specific model version. If omitted, returns the latest active version."),
    svc: ModelService = Depends(get_model_service),
) -> GetModelResponse:
    """Retrieve a model by ID."""
    model_id = _validate_model_id(model_id)
    data = await svc.get_model(model_id, version=version)
    return GetModelResponse(success=True, data=data)


@router.post(
    "",
    status_code=201,
    summary="Register a new model version (ULCA model-schema conformant)",
    responses=error_responses(409),
)
async def create_model(
    request: Request,
    payload: ModelCreateRequest,
    svc: ModelService = Depends(get_model_service),
) -> CreateModelResponse:
    """Registers a new model version in the registry. The request body
    follows ULCA's `model-schema.yml` Model object: `name`, `version`,
    `description`, `task`, `license`, `domain`, `submitter`,
    and `trainingDataset` are required;
    `refUrl`, `languages`, `isLangDetectionEnabled`, `isMultilingual`,
    `licenseUrl`, `adapterConfig`, `schema`, `benchmarks`,
    and `classInstance` are optional (see
    each field's description in the schema below for its default, if
    any). Use the 'Example Value' tab for a full worked payload.
    """
    user_id = request.headers.get("X-User-Id")
    model_id = await svc.create_model(payload, created_by=user_id)
    return CreateModelResponse(
        success=True,
        data=CreateModelData(modelId=model_id, name=payload.name, version=payload.version),
        meta=MessageMeta(message=f"Model '{payload.name}' created successfully."),
    )


@router.patch(
    "",
    summary="Partially update a model version (ULCA model-schema conformant)",
    responses=error_responses(404, 409),
)
async def update_model(
    request: Request,
    payload: ModelUpdateRequest,
    svc: ModelService = Depends(get_model_service),
) -> UpdateModelResponse:
    """Applies a partial update to an existing (modelId, version). Only
    `modelId` and `version` are required — every other field
    (`description`, `task`, `languages`, `license`, `domain`,
    `submitter`, `trainingDataset`, `adapterConfig`,
    `schema`, etc.) is optional; omit a field to leave it unchanged.
    `name` cannot be changed (modelId is derived from name+version —
    create a new version instead). `adapterConfig` is deep-merged with
    the stored value; `schema` replaces the stored value entirely.
    Use the 'Example Value' tab for a realistic partial-update payload.
    """
    user_id = request.headers.get("X-User-Id")
    await svc.update_model(payload, updated_by=user_id)
    return UpdateModelResponse(
        success=True,
        data=UpdateModelData(modelId=payload.modelId, version=payload.version),
        meta=MessageMeta(message=f"Model '{payload.modelId}' updated successfully."),
    )


@router.delete("/{model_id:path}", responses=error_responses(404, 409))
async def delete_model(
    model_id: str,
    svc: ModelService = Depends(get_model_service),
) -> DeleteModelResponse:
    """Delete a model by its hash-generated model ID."""
    await svc.delete_model(model_id)
    return DeleteModelResponse(
        success=True,
        data=DeleteModelData(modelId=model_id),
        meta=MessageMeta(message=f"Model '{model_id}' deleted successfully."),
    )
