from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from typing import Dict, Any

from db_connection import get_tenant_db_session
from models.tenant_update import TenantUpdateRequest, TenantUpdateResponse
from models.tenant_view import TenantViewResponse, ListTenantsResponse

from services.tenant_service import (
    update_tenant,
    list_tenants_by_adopter_admin,
)

from logger import logger
from middleware.adopter_auth import require_adopter_admin


router = APIRouter(
    prefix="/adopter",
    tags=["Adopter Admin - Tenant Management"],
    dependencies=[Depends(require_adopter_admin)]
)


@router.get("/tenants", response_model=ListTenantsResponse, status_code=status.HTTP_200_OK)
async def list_adopter_tenants(
    auth_context: Dict[str, Any] = Depends(require_adopter_admin),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    List all tenants owned by the current adopter admin.
    Only tenants where user_id matches the authenticated user are returned.
    """
    try:
        user_id = auth_context.get("user_id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User ID not found in authentication context"
            )
        
        return await list_tenants_by_adopter_admin(user_id, db)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Error listing adopter admin tenants: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/tenants/update", response_model=TenantUpdateResponse, status_code=status.HTTP_200_OK)
async def update_adopter_tenant(
    payload: TenantUpdateRequest,
    auth_context: Dict[str, Any] = Depends(require_adopter_admin),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    Update tenant information for a tenant owned by the current adopter admin.
    Only tenants owned by the authenticated adopter admin can be updated.
    
    Supports partial updates - only provided fields will be updated.
    """
    try:
        user_id = auth_context.get("user_id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User ID not found in authentication context"
            )
        
        return await update_tenant(payload, db, user_id=user_id)
    except HTTPException:
        raise
    except IntegrityError as ie:
        logger.error(f"Integrity error while updating tenant | tenant_id={payload.tenant_id}: {ie}")
        raise HTTPException(status_code=409, detail="Tenant update conflict (e.g., domain already exists)")
    except ValueError as ve:
        logger.error(f"Validation error while updating tenant | tenant_id={payload.tenant_id}: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        logger.exception(f"Unexpected error while updating tenant | tenant_id={payload.tenant_id}: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")
