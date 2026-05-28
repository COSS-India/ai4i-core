"""Internal endpoints — service-to-service calls, not exposed to end users."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.exceptions import EntityNotFoundError
from app.dependencies.services import get_tenant_service
from app.services.tenant_service import TenantService

router = APIRouter(tags=["Internal"])


@router.get("/tenant-plan/tenant-id/{tenant_id}")
async def get_tenant_plan(tenant_id: str, svc: TenantService = Depends(get_tenant_service)):
    try:
        tid = int(tenant_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant_id")
    try:
        return await svc.get_tenant_plan(tid)
    except EntityNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No plan found for tenant")
