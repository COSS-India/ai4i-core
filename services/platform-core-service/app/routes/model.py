"""
Model management API endpoints.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.exceptions import ValidationError
from app.core.responses import success_response
from app.dependencies.auth import get_user_id
from app.dependencies.services import get_model_service
from app.schemas.enums import TaskTypeEnum
from app.schemas.model import (
    ModelCreateRequest,
    ModelUpdateRequest,
)
from app.services.model_service import ModelService

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


@router.get("")
async def list_models(
    response: Response,
    task_type: Optional[str] = Query(
        None,
        description="Filter by task type (asr, nmt, tts, etc.).",
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
    items, total = await svc.list_models(
        task_type=_resolve_task_type(task_type),
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
    data = await svc.get_model(model_id, version=version)
    return success_response(data=data)


@router.post("")
async def create_model(
    request: Request,
    payload: ModelCreateRequest,
    svc: ModelService = Depends(get_model_service),
):
    """Create a new model version."""
    user_id = get_user_id(request)
    model_id = await svc.create_model(payload, created_by=user_id)
    return success_response(
        data={
            "modelId": model_id,
            "name": payload.name,
            "version": payload.version,
        },
        meta={"message": f"Model '{payload.name}' created successfully."},
    )


@router.patch("")
async def update_model(
    request: Request,
    payload: ModelUpdateRequest,
    svc: ModelService = Depends(get_model_service),
):
    """Update an existing model version."""
    user_id = get_user_id(request)
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
