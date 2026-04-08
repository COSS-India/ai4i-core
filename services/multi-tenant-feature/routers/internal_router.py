from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db_connection import get_tenant_db_session


from models.service_create import ListServicesResponse
from models.db_models import ServiceConfig, Tenant, TenantPlan
from services.tenant_service import (
    view_tenant_details,
    view_tenant_user_details,
    list_service,
)

from logger import logger
from middleware.auth_provider import AuthProvider


router = APIRouter(
    prefix="/internal",
    tags=["Internal router"],
    dependencies=[Depends(AuthProvider)],
)


@router.get("/view/tenant", 
            status_code=status.HTTP_200_OK,
            )
async def view_tenant(
    request: Request,
    tenant_id: str,
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    View tenant details by tenant_id (human-readable tenant identifier).

    Internal enforcement calls should not require (or attempt) role lookups in auth-service.
    """
    try:
        # Do not propagate end-user Authorization into tenant_service role resolution.
        # This internal endpoint is used for tenant subscription/status checks only.
        result = await view_tenant_details(tenant_id, db, auth_header=None)

        if not result:
            raise HTTPException(status_code=404, detail="Tenant not found")

        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Error viewing tenant details | tenant_id={tenant_id}: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")
    


@router.get("/view/user", 
            status_code=status.HTTP_200_OK,
            )
async def view_tenant_user(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    View tenant user details by auth user_id.

    Internal enforcement calls should not require (or attempt) role lookups in auth-service.
    """
    try:
        result = await view_tenant_user_details(user_id, db, auth_header=None)

        if not result:
            raise HTTPException(status_code=404, detail="Tenant user not found")

        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Error viewing tenant user details | user_id={user_id}: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")



@router.get("/list/services", 
            response_model=ListServicesResponse, 
            status_code=status.HTTP_200_OK,
            )
async def list_services_request(db: AsyncSession = Depends(get_tenant_db_session)):
    try:
        result = await list_service(db)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Error listing services: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/service-configs/tier/{tier}",
    status_code=status.HTTP_200_OK,
)
async def list_service_configs_by_tier(
    tier: str,
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """Used by policy-engine to bundle tier-scoped ServiceConfig rows into a plan."""
    try:
        r = await db.execute(
            select(ServiceConfig).where(
                ServiceConfig.tier == tier,
                ServiceConfig.is_active.is_(True),
            )
        )
        rows = r.scalars().all()
        return {
            "tier": tier,
            "services": [
                {
                    "id": s.id,
                    "service_name": s.service_name,
                    "unit_type": s.unit_type.value if hasattr(s.unit_type, "value") else str(s.unit_type),
                    "price_per_unit": float(s.price_per_unit) if s.price_per_unit is not None else None,
                    "cost_per_unit": float(s.cost_per_unit) if s.cost_per_unit is not None else float(s.price_per_unit),
                    "currency": s.currency,
                    "billing_unit_type": s.billing_unit_type,
                    "tier": s.tier,
                }
                for s in rows
            ],
        }
    except Exception as exc:
        logger.exception("Error listing service configs by tier: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/tenant-plan/tenant-id/{tenant_id}",
    status_code=status.HTTP_200_OK,
)
async def get_tenant_plan_snapshot(
    tenant_id: str,
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """Latest TenantPlan snapshot for a tenant (human-readable tenant_id)."""
    tenant = await db.scalar(select(Tenant).where(Tenant.tenant_id == tenant_id))
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tp = await db.scalar(
        select(TenantPlan)
        .where(TenantPlan.tenant_id == tenant.id)
        .order_by(TenantPlan.assigned_at.desc())
    )
    if not tp:
        raise HTTPException(status_code=404, detail="No plan assigned")
    plan_cost_val = None
    if tp.plan_cost is not None:
        try:
            plan_cost_val = float(tp.plan_cost)
        except (TypeError, ValueError):
            plan_cost_val = None
    return {
        "id": str(tp.id),
        "tenant_id": tenant_id,
        "tenant_name": tenant.organization_name,
        "plan_id": str(tp.plan_id),
        "plan_name": tp.plan_name,
        "tier": tp.tier,
        "plan_cost": plan_cost_val,
        "quota_config": tp.quota_config,
        "rate_limit_config": tp.rate_limit_config,
        "allowed_services": tp.allowed_services,
        "assigned_at": tp.assigned_at.isoformat() if tp.assigned_at else None,
    }