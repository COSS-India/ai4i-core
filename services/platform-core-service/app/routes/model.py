"""
Model management API endpoints.
"""

import logging
import re
from datetime import date, datetime
from typing import Annotated, Any, Dict, FrozenSet, List, Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.utils.route_helpers import DATE_PARAM_HELP, DateOrDatetime, split_csv
from app.core.exceptions import ValidationError
from app.dependencies.services import ModelService, get_model_service
from app.repositories.model_management.model_repository import (
    ModelListFilters,
    _range_end_exclusive,
    _range_start,
)
from app.schemas.common import MessageMeta, error_responses
from app.schemas.enums.model_management import VersionStatusEnum
from app.schemas.model_management.model_columns import (
    SORTABLE_KEYS,
    response_fields_for,
)
from app.services.pay_per_use import inference_type_cache
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
    prefix="/models/list",
    tags=["Model Management"],
)


_MODEL_ID_RE = re.compile(r"^(?=.*[a-zA-Z0-9])[a-zA-Z0-9/_-]+$")
_MODEL_ID_MAX_LEN = 255

_DATE_PARAM_HELP = DATE_PARAM_HELP
_split_csv = split_csv


def _select_fields(item: Dict[str, Any], fields: FrozenSet[str]) -> Dict[str, Any]:
    return {k: v for k, v in item.items() if k in fields}


def _parse_columns(columns: Optional[str]) -> Optional[FrozenSet[str]]:
    """Selected column ids; None means return the full item."""
    if not columns:
        return None
    requested = {p.strip() for p in columns.split(",") if p.strip()}
    if not requested:
        return None
    return frozenset(requested)


def _validate_sort(sort_by: Optional[str], sort_order: str) -> None:
    if sort_by is not None and sort_by not in SORTABLE_KEYS:
        raise ValidationError(
            message=f"sort_by must be one of: {', '.join(sorted(SORTABLE_KEYS))}",
            code="INVALID_SORT_BY",
        )
    if sort_order not in {"asc", "desc"}:
        raise ValidationError(message="sort_order must be 'asc' or 'desc'", code="INVALID_SORT_ORDER")


def _validate_date_range(created_from: Any, created_to: Any) -> None:
    if created_from is not None and created_to is not None:
        if _range_start(created_from) >= _range_end_exclusive(created_to):
            raise ValidationError(
                message="created_from must not be after created_to",
                code="INVALID_DATE_RANGE",
            )


class ModelListFilterParams:
    """Query-param dependency: the filter half of GET /models/list."""

    def __init__(
        self,
        name: Annotated[
            Optional[str],
            Query(description="Case-insensitive 'contains' match on the model name."),
        ] = None,
        version: Annotated[
            Optional[str],
            Query(description="Case-insensitive 'contains' match on the model version."),
        ] = None,
        task_types: Annotated[
            Optional[str],
            Query(description="Comma-separated task types to include."),
        ] = None,
        provider_name: Annotated[
            Optional[str],
            Query(description="Case-insensitive 'contains' match on the provider (submitter) name."),
        ] = None,
        version_status: Annotated[
            Optional[str],
            Query(description="Filter by version status: 'active' or 'deprecated'."),
        ] = None,
        created_from: Annotated[
            Optional[DateOrDatetime],
            Query(description="Models created at or after this point. " + _DATE_PARAM_HELP),
        ] = None,
        created_to: Annotated[
            Optional[DateOrDatetime],
            Query(description="Models created before this point. " + _DATE_PARAM_HELP),
        ] = None,
        include_deprecated: Annotated[
            bool,
            Query(description="Include deprecated versions. Ignored when version_status is set."),
        ] = True,
        created_by: Annotated[
            Optional[str],
            Query(description="Filter by user ID who created the model."),
        ] = None,
    ) -> None:
        self.name = name
        self.version = version
        self.task_types = task_types
        self.provider_name = provider_name
        self.version_status = version_status
        self.created_from = created_from
        self.created_to = created_to
        self.include_deprecated = include_deprecated
        self.created_by = created_by


class ModelListSortParams:
    """Query-param dependency: the sort and pagination half of GET /models/list."""

    def __init__(
        self,
        sort_by: Annotated[
            Optional[str],
            Query(
                description=(
                    "Column id to sort by: " + ", ".join(sorted(SORTABLE_KEYS)) + ". "
                    "Default: newest first."
                ),
            ),
        ] = None,
        sort_order: Annotated[
            str,
            Query(description="Sort direction when sort_by is given: asc (default) or desc."),
        ] = "asc",
        offset: Annotated[
            int,
            Query(ge=0, description="Number of items to skip (for pagination)."),
        ] = 0,
        limit: Annotated[
            int,
            Query(ge=1, le=1000, description="Maximum number of items to return. Defaults to 100."),
        ] = 100,
    ) -> None:
        self.sort_by = sort_by
        self.sort_order = sort_order
        self.offset = offset
        self.limit = limit


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


@router.get("", response_model_exclude_unset=True)
async def list_models(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    svc: Annotated[ModelService, Depends(get_model_service)],
    filters: Annotated[ModelListFilterParams, Depends()],
    paging: Annotated[ModelListSortParams, Depends()],
    columns: Annotated[
        Optional[str],
        Query(
            description=(
                "Comma-separated column ids (as returned by the model-column config entry); "
                "each row then carries only the fields those columns need. "
                "Omit to return the full item."
            ),
        ),
    ] = None,
) -> ListModelsResponse:
    """List models with optional filters, sorting and offset/limit pagination."""
    sort_by = paging.sort_by or None
    _validate_sort(sort_by, paging.sort_order)
    _validate_date_range(filters.created_from, filters.created_to)
    selected = _parse_columns(columns)

    valid_version_statuses = [e.value.lower() for e in VersionStatusEnum]
    if filters.version_status is not None and filters.version_status not in valid_version_statuses:
        raise ValidationError(
            f"Invalid version_status. Accepted values are: {valid_version_statuses}."
        )

    task_types = _split_csv(filters.task_types)
    if task_types:
        valid = {entry["name"] for entry in await inference_type_cache.get_all(db)}
        task_types = [t for t in task_types if t in valid]

    model_filters = ModelListFilters(
        name=filters.name or None,
        version=filters.version or None,
        task_types=task_types or None,
        provider_name=filters.provider_name or None,
        version_status=filters.version_status,
        created_from=filters.created_from,
        created_to=filters.created_to,
        include_deprecated=filters.include_deprecated,
        created_by=filters.created_by,
    )

    include_service_count = selected is None or "noOfServices" in selected
    items, total = await svc.list_models(
        filters=model_filters,
        sort_by=sort_by,
        sort_order=paging.sort_order,
        include_service_count=include_service_count,
        offset=paging.offset,
        limit=paging.limit,
    )

    if selected is not None:
        fields = response_fields_for(selected)
        items = [_select_fields(i, fields) for i in items]

    response.headers["X-Total-Count"] = str(total)
    return ListModelsResponse(
        success=True,
        data=items,
        meta=ModelListMeta(total=total, offset=paging.offset, limit=paging.limit),
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
