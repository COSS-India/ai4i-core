"""
Tenant Policy Mapping routes.
POST   /tenants/{tenant_id}/policies
GET    /tenants/{tenant_id}/policies
DELETE /tenants/{tenant_id}/policies/{policy_id}
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_adopter_admin
from app.db.session import get_db
from app.models.schemas import (
    Meta,
    PolicyOut,
    TenantPolicyAssign,
    TenantPolicyListResponse,
    TenantPolicyOut,
)
from app.services.tenant_policy_service import TenantPolicyService

router = APIRouter(prefix="/tenants", tags=["Tenant Policy Mapping"], dependencies=[Depends(require_adopter_admin)])


def _svc(db: AsyncSession = Depends(get_db)) -> TenantPolicyService:
    return TenantPolicyService(db)


@router.post(
    "/{tenant_id}/policies",
    response_model=TenantPolicyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a policy to a tenant",
)
async def assign_policy(
    tenant_id: str, body: TenantPolicyAssign, svc: TenantPolicyService = Depends(_svc)
):
    return await svc.assign(tenant_id, body)


@router.get(
    "/{tenant_id}/policies",
    response_model=TenantPolicyListResponse,
    summary="List all policies for a tenant (assigned + global)",
)
async def list_tenant_policies(
    tenant_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    svc: TenantPolicyService = Depends(_svc),
):
    rows, total = await svc.list_for_tenant(tenant_id, page=page, limit=limit)
    data = [PolicyOut.model_validate(r) for r in rows]
    return TenantPolicyListResponse(data=data, meta=Meta(total=total, page=page, limit=limit))


@router.delete(
    "/{tenant_id}/policies/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unassign a policy from a tenant",
)
async def unassign_policy(
    tenant_id: str, policy_id: UUID, svc: TenantPolicyService = Depends(_svc)
):
    await svc.unassign(tenant_id, policy_id)
