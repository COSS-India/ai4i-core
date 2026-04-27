"""
Service management routes.

Path layout (mounted under /api/v1):
  GET    /services                              — list services with filters
  GET    /services/try-it-service-list          — public NMT-only listing
  GET    /services/policies                     — list services + policies
  POST   /services/{service_id}                 — get service detail (body variant)
  POST   /services                              — create a new service
  PATCH  /services                              — update a service
  DELETE /services/{service_id}                 — delete a service
  PATCH  /services/{service_id}/health          — update service health
  POST   /services/{service_id}/policy          — set service policy

Permissions are enforced by the shared AuthProvider; the try-it endpoint
intentionally bypasses auth.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from app.core.exceptions import ValidationError
from app.core.responses import success_response
from app.dependencies.auth import AuthProvider, OptionalAuthProvider, get_user_id
from app.dependencies.services import get_service_service
from app.schemas.enums import TaskTypeEnum
from app.schemas.service import (
    ServiceCreateRequest,
    ServiceHealthUpdateRequest,
    ServicePolicyUpdateRequest,
    ServiceUpdateRequest,
)
from app.services.service_service import ServiceService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/services",
    tags=["Service Management"],
)


def _resolve_task_type(task_type: Optional[str]) -> Optional[str]:
    if not task_type or task_type.lower() == "none":
        return None
    return TaskTypeEnum(task_type).value


# ── Public try-it (no auth) — must be declared before /{service_id} ──


@router.get(
    "/try-it-service-list",
    summary="Public try-it service listing API",
    dependencies=[Depends(OptionalAuthProvider)],
)
async def list_try_it_services(
    task_type: str = Query(
        ...,
        description="Task type (currently only 'nmt' is supported).",
    ),
    svc: ServiceService = Depends(get_service_service),
):
    """List published services available for public trial — currently NMT only."""
    if not task_type or task_type.lower() != TaskTypeEnum.nmt.value:
        raise ValidationError(
            message="Try-it is not available for this task type.",
            code="TRY_IT_UNSUPPORTED",
        )
    items = await svc.list_services(
        task_type=TaskTypeEnum.nmt.value, is_published=True
    )
    return success_response(data=items, meta={"total": len(items)})


# ── Authenticated routes ──


@router.get("", dependencies=[Depends(AuthProvider)])
async def list_services(
    task_type: Optional[str] = Query(
        None, description="Filter by task type."
    ),
    is_published: Optional[bool] = Query(
        None,
        description="True = published only, False = unpublished only, omit for all.",
    ),
    created_by: Optional[str] = Query(
        None, description="Filter by user ID who created the service."
    ),
    svc: ServiceService = Depends(get_service_service),
):
    items = await svc.list_services(
        task_type=_resolve_task_type(task_type),
        is_published=is_published,
        created_by=created_by,
    )
    return success_response(data=items, meta={"total": len(items)})


@router.get("/policies", dependencies=[Depends(AuthProvider)])
async def list_service_policies(
    task_type: Optional[str] = Query(None, description="Filter by task type."),
    svc: ServiceService = Depends(get_service_service),
):
    items = await svc.list_policies(task_type=_resolve_task_type(task_type))
    return success_response(data={"services": items}, meta={"total": len(items)})


@router.post("/{service_id:path}/policy", dependencies=[Depends(AuthProvider)])
async def upsert_service_policy(
    service_id: str,
    payload: ServicePolicyUpdateRequest,
    request: Request,
    svc: ServiceService = Depends(get_service_service),
):
    user_id = get_user_id(request)
    result = await svc.upsert_policy(service_id, payload.policy, updated_by=user_id)
    return success_response(data=result)


@router.patch("/{service_id:path}/health", dependencies=[Depends(AuthProvider)])
async def update_service_health(
    service_id: str,
    payload: ServiceHealthUpdateRequest,
    svc: ServiceService = Depends(get_service_service),
):
    await svc.update_service_health(service_id, payload)
    return success_response(
        data={"serviceId": service_id, "status": payload.status},
        meta={"message": f"Service '{service_id}' health status updated."},
    )


@router.post("/{service_id:path}", dependencies=[Depends(AuthProvider)])
async def view_service(
    service_id: str,
    svc: ServiceService = Depends(get_service_service),
):
    """Get full service detail — embedded model card included."""
    data = await svc.get_service_detail(service_id)
    return success_response(data=data)


@router.post("", dependencies=[Depends(AuthProvider)])
async def create_service(
    request: Request,
    payload: ServiceCreateRequest,
    svc: ServiceService = Depends(get_service_service),
):
    user_id = get_user_id(request)
    service_id = await svc.create_service(payload, created_by=user_id)
    return success_response(
        data={"serviceId": service_id, "name": payload.name},
        meta={"message": f"Service '{payload.name}' created successfully."},
    )


@router.patch("", dependencies=[Depends(AuthProvider)])
async def update_service(
    request: Request,
    payload: ServiceUpdateRequest,
    svc: ServiceService = Depends(get_service_service),
):
    user_id = get_user_id(request)
    await svc.update_service(payload, updated_by=user_id)
    return success_response(
        data={"serviceId": payload.serviceId},
        meta={"message": f"Service '{payload.serviceId}' updated successfully."},
    )


@router.delete("/{service_id:path}", dependencies=[Depends(AuthProvider)])
async def delete_service(
    service_id: str,
    svc: ServiceService = Depends(get_service_service),
):
    await svc.delete_service(service_id)
    return success_response(
        data={"serviceId": service_id},
        meta={"message": f"Service '{service_id}' deleted successfully."},
    )
