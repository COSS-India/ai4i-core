"""
Service management API endpoints.
"""

import logging
import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.exceptions import AppError, ValidationError
from app.core.responses import success_response
from app.dependencies.services import ServiceService, get_service_service
from app.schemas.enums.model_management import TaskTypeEnum
from app.schemas.model_management.service import (
    ServiceBulkEndpointUpdateRequest,
    ServiceCreateRequest,
    ServiceUpdateRequest,
    validate_service_id,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/services",
    tags=["Service Management"],
)


def _resolve_task_type(task_type: Optional[str]) -> Optional[str]:
    if not task_type or task_type.lower() == "none":
        return None
    try:
        return TaskTypeEnum(task_type).value
    except ValueError:
        valid = [e.value for e in TaskTypeEnum]
        raise ValidationError(f"Invalid task_type '{task_type}'. Must be one of: {valid}")


# ── RBAC-aware response filtering (AI4IDS-1816) ──────────────────────────────
#
# service.read (permission id 51) is deliberately granted to every role,
# including Tenant Admin/User/Guest — every inference-submission flow in the
# frontend depends on GET /services to resolve a serviceId before calling
# NMT/ASR/TTS/etc, so this endpoint can't be locked down to Admin/Moderator
# without breaking inference for all non-admin users. What can and should be
# fixed: service_to_dict() returns internal fields (api_key, policy, cost/
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
# model.inferenceEndPoint.adapter_config to build the actual Triton request.
# Dropping "model" here breaks inference for every service (AI4IDS-2562
# investigation) — the model card is Triton tensor-mapping/schema config, not
# a secret (no api_key/policy/billing inside it), so it's safe to allow.
_NON_ADMIN_SERVICE_FIELDS = {
    "serviceId",
    "name",
    "modelId",
    "modelVersion",
    "serviceDescription",
    "endpoint",
    "taskType",
    "isPublished",
    "task",
    "languages",
    "versionStatus",
    "model",
    "tierIds",  # required by inference-service tier enforcement
}


def _permission_ids(request: Request) -> set[int]:
    """Mirrors app/routes/metering.py's helper — X-Permission-IDS is injected
    by the gateway after JWT validation."""
    raw = request.headers.get("X-Permission-IDS", "")
    return {int(m) for m in re.findall(r"\d+", raw)}


def _is_platform_admin(request: Request) -> bool:
    return bool(_permission_ids(request) & {_ROLE_ADMIN, _ROLE_MODERATOR})


def _filter_service_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    """Strip internal/sensitive fields (api_key, policy, billing, health,
    hardware, tiers, audit) down to what non-admin/public callers need."""
    return {k: v for k, v in item.items() if k in _NON_ADMIN_SERVICE_FIELDS}


@router.get(
    "/try-it-service-list",
    summary="List Try-It Services",
)
async def list_try_it_services(
    task_type: str = Query(
        ...,
        description="Task type. Currently supports 'nmt'.",
    ),
    svc: ServiceService = Depends(get_service_service),
):
    """List published services available for public trial."""
    if not task_type or task_type.lower() != TaskTypeEnum.nmt.value:
        raise ValidationError(
            message="Try-it is not available for this task type.",
            code="TRY_IT_UNSUPPORTED",
        )
    items, total = await svc.list_services(
        task_type=TaskTypeEnum.nmt.value, is_published=True
    )
    # This endpoint has no auth at all (see api_permissions.json: try-it is
    # public) — always filtered, never the admin/full view.
    items = [_filter_service_fields(i) for i in items]
    return success_response(data={"services": items}, meta={"total": total})


@router.get("")
async def list_services(
    request: Request,
    response: Response,
    task_type: Optional[str] = Query(
        None, description="Filter by task type."
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
):
    """List services with optional filters and offset/limit pagination."""
    items, total = await svc.list_services(
        task_type=_resolve_task_type(task_type),
        is_published=is_published,
        created_by=created_by,
        offset=offset,
        limit=limit,
    )
    if not _is_platform_admin(request):
        items = [_filter_service_fields(i) for i in items]
    response.headers["X-Total-Count"] = str(total)
    return success_response(
        data={"services": items},
        meta={"total": total, "offset": offset, "limit": limit},
    )


@router.get("/{service_id:path}", summary="Retrieve Service")
async def view_service(
    request: Request,
    service_id: str,
    svc: ServiceService = Depends(get_service_service),
):
    """Retrieve full service details."""
    try:
        validate_service_id(service_id)
    except ValueError as exc:
        raise ValidationError(message=str(exc), code="INVALID_SERVICE_ID")
    data = await svc.get_service_detail(service_id)
    if not _is_platform_admin(request):
        data = _filter_service_fields(data)
    return success_response(data=data)


@router.post("")
async def create_service(
    request: Request,
    payload: ServiceCreateRequest,
    svc: ServiceService = Depends(get_service_service),
):
    """Create a new service."""
    user_id = request.headers.get("X-User-Id")
    service_id = await svc.create_service(payload, created_by=user_id)
    return success_response(
        data={"serviceId": service_id, "name": payload.name},
        meta={"message": f"Service '{payload.name}' created successfully."},
    )


@router.patch("")
async def update_service(
    request: Request,
    payload: ServiceUpdateRequest | ServiceBulkEndpointUpdateRequest,
    svc: ServiceService = Depends(get_service_service),
):
    """Update an existing service, or update multiple services' endpoints in
    one call by sending {"services": [{"serviceId", "endpoint"}, ...]}."""
    user_id = request.headers.get("X-User-Id")
    if isinstance(payload, ServiceBulkEndpointUpdateRequest):
        updated_ids = await svc.update_service_endpoints(
            payload.services, updated_by=user_id
        )
        return success_response(
            data={"serviceIds": updated_ids},
            meta={"message": f"{len(updated_ids)} service endpoint(s) updated successfully."},
        )
    await svc.update_service(payload, updated_by=user_id)
    return success_response(
        data={"serviceId": payload.serviceId},
        meta={"message": f"Service '{payload.serviceId}' updated successfully."},
    )


@router.delete("/{service_id:path}")
async def delete_service(
    service_id: str,
    svc: ServiceService = Depends(get_service_service),
):
    """Delete a service by its service ID."""
    await svc.delete_service(service_id)
    return success_response(
        data={"serviceId": service_id},
        meta={"message": f"Service '{service_id}' deleted successfully."},
    )
