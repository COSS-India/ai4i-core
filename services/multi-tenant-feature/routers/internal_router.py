from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from db_connection import get_tenant_db_session


from models.service_create import ListServicesResponse
from services.tenant_service import (
    view_tenant_details,
    view_tenant_user_details,
    list_service
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