"""
Service management API endpoints.
"""

import logging
import re
from typing import Any, Dict, Optional, Union

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppError, ValidationError
from app.dependencies.services import ServiceService, get_service_service
from app.schemas.common import MessageMeta, TotalMeta, error_responses
from app.schemas.enums.model_management import TaskTypeEnum
from app.services.pay_per_use import inference_type_cache
from app.schemas.model_management.service import (
    CreateServiceData,
    CreateServiceResponse,
    DeleteServiceData,
    DeleteServiceResponse,
    GetServiceResponse,
    ListServicesResponse,
    ListTryItServicesResponse,
    ServiceBulkEndpointUpdateRequest,
    ServiceCreateRequest,
    ServiceListMeta,
    ServicesData,
    ServiceUpdateRequest,
    UpdateServiceData,
    UpdateServiceEndpointsData,
    UpdateServiceEndpointsResponse,
    UpdateServiceResponse,
    validate_service_id,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/services",
    tags=["Service Management"],
)


# ── RBAC-aware response filtering (AI4IDS-1816) ──────────────────────────────
#
# service.read (permission id 51) is deliberately granted to every role,
# including Tenant Admin/User/Guest — every inference-submission flow in the
# frontend depends on GET /services to resolve a serviceId before calling
# NMT/ASR/TTS/etc, so this endpoint can't be locked down to Admin/Moderator
# without breaking inference for all non-admin users. What can and should be
# fixed: service_to_dict() returns internal fields (api_key, cost/
# billing, health, hardware, tier assignments) that no non-admin caller needs
# or should see. Non-admin callers (and the fully public try-it endpoint) get
# an allow-listed subset instead; Admin/Moderator keep the full response.

_ROLE_ADMIN = 1
_ROLE_MODERATOR = 2

# Only fields actually consumed by the inference-submission flow and the
# public try-it picker (confirmed against every *Service.ts call site and
# shared picker component in frontend/simple-ui/src), plus "model" — required
# by inference-service's own internal GET /services/{id} call (no identity
# headers, so it always hits this filtered path), which reads
# model.adapterConfig and model.schema to build the actual Triton request.
# Dropping "model" here breaks inference for every service (AI4IDS-2562
# investigation) — the model card is Triton tensor-mapping/schema config, not
# a secret (no api_key/billing inside it), so it's safe to allow.
_NON_ADMIN_SERVICE_FIELDS = {
    "serviceId",
    "name",
    "modelId",
    "modelVersion",
    "description",  # ULCA name for serviceDescription
    "serviceDescription",
    "endpoint",
    "taskType",
    "isPublished",
    "isTryItDefault",
    "task",
    "languages",
    "versionStatus",
    "model",
    "tierIds",  # required by inference-service tier enforcement
    # NOTE: the new nested `inferenceEndPoint` object is deliberately NOT
    # in this allow-list. It bundles `infraDescription`
    # (== the existing `hardwareDescription`, already admin-only) together
    # with the public-safe bits (callbackUrl, supported*Formats, ...) in one
    # object, and _filter_service_fields below only does a shallow top-level
    # filter — allow-listing the whole object would leak infraDescription to
    # non-admins. Exposing a redacted version of it is a separate follow-up
    # if a non-admin caller ever needs these fields.
}


def _permission_ids(request: Request) -> set[int]:
    """Mirrors app/routes/metering.py's helper — X-Permission-IDS is injected
    by the gateway after JWT validation."""
    raw = request.headers.get("X-Permission-IDS", "")
    return {int(m) for m in re.findall(r"\d+", raw)}


def _is_platform_admin(request: Request) -> bool:
    return bool(_permission_ids(request) & {_ROLE_ADMIN, _ROLE_MODERATOR})


def _filter_service_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    """Strip internal/sensitive fields (api_key, billing, health,
    hardware, tiers, audit) down to what non-admin/public callers need."""
    return {k: v for k, v in item.items() if k in _NON_ADMIN_SERVICE_FIELDS}


_TRY_IT_SUPPORTED_TASK_TYPES = {TaskTypeEnum.nmt.value, TaskTypeEnum.llm.value}


@router.get(
    "/try-it-service-list",
    summary="List Try-It Services",
    # _filter_service_fields strips sensitive keys (api_key, billing, health,
    # ...) from the dict entirely for non-admin/public callers — they must
    # stay absent from the JSON, not reappear as an explicit `null` just
    # because ServiceListItem declares them. exclude_unset achieves that: it
    # drops only fields that were never in the source dict, while a field
    # that legitimately IS None in the data (e.g. licenseUrl for an admin)
    # still comes through as explicit null, unchanged.
    response_model_exclude_unset=True,
)
async def list_try_it_services(
    task_types: str = Query(
        ...,
        description="Comma-separated task types",
    ),
    svc: ServiceService = Depends(get_service_service),
) -> ListTryItServicesResponse:
    """List published services available for public trial."""
    _task_types = [t.strip().lower() for t in task_types.split(",") if t.strip().lower() in _TRY_IT_SUPPORTED_TASK_TYPES]
    if not _task_types:
        raise ValidationError(
            message="Try-it is not available for this task type.",
            code="TRY_IT_UNSUPPORTED",
        )
    items, total = await svc.list_services(
        task_types=_task_types, is_published=True
    )
    # This endpoint has no auth at all (see api_permissions.json: try-it is
    # public) — always filtered, never the admin/full view.
    items = [_filter_service_fields(i) for i in items]
    return ListTryItServicesResponse(
        success=True, data=ServicesData(services=items), meta=TotalMeta(total=total)
    )


@router.get("", response_model_exclude_unset=True)
async def list_services(
    request: Request,
    response: Response,
    task_types: Optional[str] = Query(
        None,
        description="Comma-separated task types to include. A single value is a one-element list.",
    ),
    is_published: Optional[bool] = Query(
        None,
        description="Filter by publication status: true for published only, false for unpublished only.",
    ),
    created_by: Optional[str] = Query(
        None, description="Filter by user ID who created the service."
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Number of items to skip (for pagination).",
    ),
    limit: Optional[int] = Query(
        None,
        ge=1,
        le=1000,
        description="Maximum number of items to return. Omit to return all services.",
    ),
    svc: ServiceService = Depends(get_service_service),
    db: AsyncSession = Depends(get_db),
) -> ListServicesResponse:
    """List services with optional filters and offset/limit pagination."""
    # ONE task-type filter param: a drill-down is just a one-element list, so a
    # separate single param would only recreate union/precedence ambiguity.
    # Parsed leniently: names outside the catalogue (e.g. entries with no
    # registered models) are skipped rather than failing the whole request —
    # they can't match any row anyway.
    #
    # The allowlist is the live catalogue, not TaskTypeEnum. Only the validation
    # source changed: mm_models/mm_services are still filtered by name, since
    # their task type is a JSONB string, not a foreign key.
    _task_types = []
    if task_types:
        valid = {entry["name"] for entry in await inference_type_cache.get_all(db)}
        _task_types = [t.strip().lower() for t in task_types.split(",") if t.strip().lower() in valid]
    items, total = await svc.list_services(
        task_types=_task_types or None,
        is_published=is_published,
        created_by=created_by,
        offset=offset,
        limit=limit,
    )
    if not _is_platform_admin(request):
        items = [_filter_service_fields(i) for i in items]
    response.headers["X-Total-Count"] = str(total)
    return ListServicesResponse(
        success=True,
        data=ServicesData(services=items),
        meta=ServiceListMeta(total=total, offset=offset, limit=limit),
    )


@router.get(
    "/{service_id:path}",
    summary="Retrieve Service",
    responses=error_responses(404),
    response_model_exclude_unset=True,
)
async def view_service(
    request: Request,
    service_id: str,
    svc: ServiceService = Depends(get_service_service),
) -> GetServiceResponse:
    """Retrieve full service details."""
    try:
        validate_service_id(service_id)
    except ValueError as exc:
        raise ValidationError(message=str(exc), code="INVALID_SERVICE_ID")
    data = await svc.get_service_detail(service_id)
    if not _is_platform_admin(request):
        data = _filter_service_fields(data)
    return GetServiceResponse(success=True, data=data)


@router.post("", responses=error_responses(400, 409))
async def create_service(
    request: Request,
    payload: ServiceCreateRequest,
    svc: ServiceService = Depends(get_service_service),
) -> CreateServiceResponse:
    """Create a new service."""
    user_id = request.headers.get("X-User-Id")
    service_id = await svc.create_service(payload, created_by=user_id)
    return CreateServiceResponse(
        success=True,
        data=CreateServiceData(serviceId=service_id, name=payload.name),
        meta=MessageMeta(message=f"Service '{payload.name}' created successfully."),
    )


@router.patch("", responses=error_responses(400, 404, 409))
async def update_service(
    request: Request,
    payload: ServiceUpdateRequest | ServiceBulkEndpointUpdateRequest,
    svc: ServiceService = Depends(get_service_service),
) -> Union[UpdateServiceResponse, UpdateServiceEndpointsResponse]:
    """Update an existing service, or update multiple services' endpoints in
    one call by sending {"services": [{"serviceId", "endpoint"}, ...]}."""
    user_id = request.headers.get("X-User-Id")
    if isinstance(payload, ServiceBulkEndpointUpdateRequest):
        updated_ids = await svc.update_service_endpoints(
            payload.services, updated_by=user_id
        )
        return UpdateServiceEndpointsResponse(
            success=True,
            data=UpdateServiceEndpointsData(serviceIds=updated_ids),
            meta=MessageMeta(message=f"{len(updated_ids)} service endpoint(s) updated successfully."),
        )
    await svc.update_service(payload, updated_by=user_id)
    return UpdateServiceResponse(
        success=True,
        data=UpdateServiceData(serviceId=payload.serviceId),
        meta=MessageMeta(message=f"Service '{payload.serviceId}' updated successfully."),
    )


@router.delete("/{service_id:path}", responses=error_responses(404, 409))
async def delete_service(
    service_id: str,
    svc: ServiceService = Depends(get_service_service),
) -> DeleteServiceResponse:
    """Delete a service by its service ID."""
    await svc.delete_service(service_id)
    return DeleteServiceResponse(
        success=True,
        data=DeleteServiceData(serviceId=service_id),
        meta=MessageMeta(message=f"Service '{service_id}' deleted successfully."),
    )
