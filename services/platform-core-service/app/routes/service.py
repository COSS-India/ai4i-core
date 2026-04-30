"""
Service management API endpoints.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.exceptions import ValidationError
from app.core.responses import platform_success_response
from app.dependencies.auth import get_user_id
from app.dependencies.services import get_service_service
from app.schemas.enums import TaskTypeEnum
from app.schemas.service import (
    ServiceCreateRequest,
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
    try:
        return TaskTypeEnum(task_type).value
    except ValueError:
        valid = [e.value for e in TaskTypeEnum]
        raise ValidationError(f"Invalid task_type '{task_type}'. Must be one of: {valid}")


@router.get(
    "/try-it-service-list",
    summary="List Try-It Services",
)
async def list_try_it_services(
    request: Request,
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
    items, _ = await svc.list_services(
        task_type=TaskTypeEnum.nmt.value, is_published=True
    )
    request_id = getattr(request.state, "platform_request_id", None)
    return platform_success_response(data=items, request_id=request_id)


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
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Maximum number of items to return. Defaults to 100.",
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
    response.headers["X-Total-Count"] = str(total)
    request_id = getattr(request.state, "platform_request_id", None)
    return platform_success_response(data=items, request_id=request_id)


@router.get("/{service_id:path}", summary="Retrieve Service")
async def view_service(
    request: Request,
    service_id: str,
    svc: ServiceService = Depends(get_service_service),
):
    """Retrieve full service details."""
    data = await svc.get_service_detail(service_id)
    request_id = getattr(request.state, "platform_request_id", None)
    return platform_success_response(data=data, request_id=request_id)


@router.post("")
async def create_service(
    request: Request,
    payload: ServiceCreateRequest,
    svc: ServiceService = Depends(get_service_service),
):
    """Create a new service."""
    user_id = get_user_id(request)
    service_id = await svc.create_service(payload, created_by=user_id)
    request_id = getattr(request.state, "platform_request_id", None)
    return platform_success_response(
        data={"serviceId": service_id, "name": payload.name},
        request_id=request_id,
        message=f"Service '{payload.name}' created successfully.",
    )


@router.patch("")
async def update_service(
    request: Request,
    payload: ServiceUpdateRequest,
    svc: ServiceService = Depends(get_service_service),
):
    """Update an existing service."""
    user_id = get_user_id(request)
    await svc.update_service(payload, updated_by=user_id)
    request_id = getattr(request.state, "platform_request_id", None)
    return platform_success_response(
        data={"serviceId": payload.serviceId},
        request_id=request_id,
        message=f"Service '{payload.serviceId}' updated successfully.",
    )


@router.delete("/{service_id:path}")
async def delete_service(
    request: Request,
    service_id: str,
    svc: ServiceService = Depends(get_service_service),
):
    """Delete a service by its hash-generated service ID."""
    await svc.delete_service(service_id)
    request_id = getattr(request.state, "platform_request_id", None)
    return platform_success_response(
        data={"serviceId": service_id},
        request_id=request_id,
        message=f"Service '{service_id}' deleted successfully.",
    )
