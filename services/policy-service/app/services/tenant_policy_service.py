"""Business logic for Tenant-Policy mapping."""
from typing import Sequence
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import PiiPolicy
from app.models.schemas import TenantPolicyAssign, TenantPolicyOut
from app.repositories.tenant_policy_repository import TenantPolicyRepository
from app.repositories.policy_repository import PolicyRepository


class TenantPolicyService:
    def __init__(self, db: AsyncSession):
        self.repo = TenantPolicyRepository(db)
        self.policy_repo = PolicyRepository(db)

    async def assign(self, tenant_id: str, data: TenantPolicyAssign) -> TenantPolicyOut:
        policy = await self.policy_repo.get(data.policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Policy not found"}})
        if policy.is_global:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "VALIDATION_ERROR", "message": "Cannot explicitly assign a global policy"}},
            )
        existing = await self.repo.get_assignment(tenant_id, data.policy_id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail={"error": {"code": "CONFLICT", "message": "Policy already assigned to this tenant"}},
            )
        obj = await self.repo.assign(tenant_id, data.policy_id)
        return TenantPolicyOut.model_validate(obj)

    async def list_for_tenant(
        self, tenant_id: str, page: int, limit: int
    ) -> tuple[Sequence[PiiPolicy], int]:
        return await self.repo.list_for_tenant(tenant_id, page=page, limit=min(limit, 100))

    async def unassign(self, tenant_id: str, policy_id: UUID) -> None:
        removed = await self.repo.unassign(tenant_id, policy_id)
        if not removed:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "NOT_FOUND", "message": "Assignment not found"}},
            )
