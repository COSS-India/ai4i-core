"""Tenant + tenant-user CRUD routes — thin handlers; logic in TenantService."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.core.responses import success_response, to_response
from app.dependencies.auth import get_current_user
from app.dependencies.services import get_tenant_service
from app.models.tenant import TenantStatus
from app.models.user import User
from app.schemas.tenant import (
    TenantCreate,
    TenantResponse,
    TenantStatusUpdate,
    TenantUpdate,
    TenantUserCreate,
    TenantUserCreateResponse,
    TenantUserStatusUpdate,
    TenantUserUpdate,
)
from app.services.tenant_service import TenantService

router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    tenant = await svc.create_tenant(body, current_user, background_tasks)
    return success_response(data=to_response(tenant, TenantResponse))


@router.get("")
async def list_tenants(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status_filter: Optional[TenantStatus] = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    tenants = await svc.list_tenants(current_user, offset, limit, status_filter)
    return success_response(data=[to_response(t, TenantResponse) for t in tenants])


@router.get("/{tenant_id}")
async def get_tenant(
    tenant_id: int,
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    tenant = await svc.get_tenant(current_user, tenant_id)
    return success_response(data=to_response(tenant, TenantResponse))


@router.patch("/{tenant_id}")
async def update_tenant(
    tenant_id: int,
    body: TenantUpdate,
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    tenant = await svc.update_tenant(current_user, tenant_id, body)
    return success_response(data=to_response(tenant, TenantResponse))


@router.patch("/{tenant_id}/status")
async def update_tenant_status(
    tenant_id: int,
    body: TenantStatusUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    tenant = await svc.update_tenant_status(
        current_user, tenant_id, body, background_tasks
    )
    return success_response(data=to_response(tenant, TenantResponse))


@router.get("/{tenant_id}/plan")
async def get_tenant_plan(
    tenant_id: int,
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    plan = await svc.get_tenant_plan(tenant_id)
    return success_response(data=plan)


@router.get("/{tenant_id}/users")
async def list_tenant_users(
    tenant_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    users = await svc.list_tenant_users(current_user, tenant_id, offset, limit)
    data = await svc.build_tenant_user_responses(users)
    return success_response(data=data)


@router.post("/{tenant_id}/users", status_code=status.HTTP_201_CREATED)
async def create_tenant_user(
    tenant_id: int,
    body: TenantUserCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    user_id_str, setup_token = await svc.create_tenant_user(
        current_user, tenant_id, body, background_tasks
    )
    return success_response(
        data=TenantUserCreateResponse(user_id=user_id_str, setup_token=setup_token).model_dump()
    )


@router.patch("/{tenant_id}/users/{user_id}/status")
async def update_tenant_user_status(
    tenant_id: int,
    user_id: UUID,
    body: TenantUserStatusUpdate,
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    target = await svc.update_tenant_user_status(current_user, tenant_id, user_id, body)
    return success_response(data=await svc.build_tenant_user_response(target))


@router.patch("/{tenant_id}/users/{user_id}")
async def update_tenant_user(
    tenant_id: int,
    user_id: UUID,
    body: TenantUserUpdate,
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    target = await svc.update_tenant_user(current_user, tenant_id, user_id, body)
    return success_response(data=await svc.build_tenant_user_response(target))


@router.delete("/{tenant_id}/users/{user_id}")
async def delete_tenant_user(
    tenant_id: int,
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    await svc.delete_tenant_user(current_user, tenant_id, user_id)
    return success_response(data={"user_id": str(user_id), "deleted": True})
