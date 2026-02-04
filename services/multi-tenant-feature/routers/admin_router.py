from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from db_connection import get_tenant_db_session , get_auth_db_session
from models.tenant_create import TenantRegisterRequest, TenantRegisterResponse
from models.user_create import UserRegisterRequest, UserRegisterResponse
from models.tenant_status import TenantStatusUpdateRequest, TenantStatusUpdateResponse
from models.user_status import TenantUserStatusUpdateRequest, TenantUserStatusUpdateResponse
from models.tenant_update import TenantUpdateRequest, TenantUpdateResponse
from models.tenant_view import TenantViewResponse, ListTenantsResponse
from models.user_view import TenantUserViewResponse, ListUsersResponse
from models.user_update import TenantUserUpdateRequest , TenantUserUpdateResponse
from models.user_delete import TenantUserDeleteRequest , TenantUserDeleteResponse

from services.tenant_service import (
    create_new_tenant,
    register_user,
    update_tenant_status,
    update_tenant_user_status,
    update_tenant,
    delete_tenant_user,
    update_tenant_user,
    view_tenant_details,
    view_tenant_user_details,
    list_all_tenants,
    list_all_users,
)

from logger import logger
from middleware.auth_provider import AuthProvider


router = APIRouter(
    prefix="/admin", 
    tags=["Tenants registeration"],
    dependencies=[Depends(AuthProvider)]
)

@router.post("/register/tenant", response_model=TenantRegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_tenant_request(
    payload: TenantRegisterRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_tenant_db_session),
):
    try:
        response = await create_new_tenant(payload, db, background_tasks)

        logger.info(f"Tenant registered successfully. Tenant Domain: {payload.domain}, Email: {payload.contact_email}")

        return response

    except HTTPException:
        raise
    except IntegrityError as ie:
        logger.error(f"Integrity error during tenant registration: {ie}")
        raise HTTPException(status_code=400, detail="Tenant with given domain or email already exists")
    except ValueError as ve:
        logger.error(f"Value error during tenant registration: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        logger.exception(f"Error registering tenant: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")
    



@router.post("/register/users",response_model=UserRegisterResponse,status_code=status.HTTP_201_CREATED,)
async def register_user_request(
    payload: UserRegisterRequest,
    background_tasks: BackgroundTasks,
    tenant_db: AsyncSession = Depends(get_tenant_db_session),
    auth_db: AsyncSession = Depends(get_auth_db_session),
):
    try:
        return await register_user(payload, tenant_db, auth_db, background_tasks)

    except HTTPException:
        raise
    except IntegrityError as ie:
        logger.error(f"Integrity error during user registration: {ie}")
        raise HTTPException(status_code=409, detail="Username or email already exists")
    except ValueError as ve:
        logger.error(f"Validation error during user registration: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        logger.exception(f"Unexpected error during user registration: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")





@router.patch("/update/tenants/status" , response_model=TenantStatusUpdateResponse , status_code=status.HTTP_200_OK)
async def change_tenant_status(payload: TenantStatusUpdateRequest, db: AsyncSession = Depends(get_tenant_db_session),):
    try:
        return await update_tenant_status(payload, db)

    except HTTPException:
        raise
    except IntegrityError as ie:
        logger.error(f"Integrity error while updating tenant status | tenant={payload.tenant_id}: {ie}")
        raise HTTPException(status_code=409, detail="Tenant status update conflict")
    except ValueError as ve:
        logger.error(f"Validation error while updating tenant status | tenant={payload.tenant_id}: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        logger.exception(f"Unexpected error while updating tenant status | tenant={payload.tenant_id}: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/update/users/status", response_model=TenantUserStatusUpdateResponse, status_code=status.HTTP_200_OK)
async def change_tenant_user_status(payload: TenantUserStatusUpdateRequest, db: AsyncSession = Depends(get_tenant_db_session)):
    try:
        return await update_tenant_user_status(payload, db)

    except HTTPException:
        raise
    except IntegrityError as ie:
        logger.error(f"Integrity error while updating tenant user status | tenant={payload.tenant_id} user_id={payload.user_id}: {ie}")
        raise HTTPException(status_code=409, detail="User status update conflict",)
    except ValueError as ve:
        logger.error(f"Validation error while updating tenant user status | "f"tenant={payload.tenant_id} user_id={payload.user_id}: {ve}")
        raise HTTPException(status_code=400, detail=str(ve),)
    except Exception as exc:
        logger.exception(f"Unexpected error while updating tenant user status | tenant={payload.tenant_id} user_id={payload.user_id}: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/update/user", response_model=TenantUserUpdateResponse, status_code=status.HTTP_200_OK)
async def update_tenant_user_info(
    payload: TenantUserUpdateRequest,
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    Update tenant user information (username, email, is_approved).
    Supports partial updates - only provided fields will be updated.
    """
    try:
        return await update_tenant_user(payload, db)
    except HTTPException:
        raise
    except IntegrityError as ie:
        logger.error(
            f"Integrity error while updating tenant user | tenant_id={payload.tenant_id} user_id={payload.user_id}: {ie}"
        )
        raise HTTPException(
            status_code=409,
            detail="Tenant user update conflict (e.g., email already exists)",
        )
    except ValueError as ve:
        logger.error(
            f"Validation error while updating tenant user | tenant_id={payload.tenant_id} user_id={payload.user_id}: {ve}"
        )
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        logger.exception(
            f"Unexpected error while updating tenant user | tenant_id={payload.tenant_id} user_id={payload.user_id}: {exc}"
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/delete/user", response_model=TenantUserDeleteResponse, status_code=status.HTTP_200_OK)
async def delete_tenant_user_endpoint(
    payload: TenantUserDeleteRequest,
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    Delete a tenant user and cascade deletions to related records.
    """
    try:
        return await delete_tenant_user(payload, db)
    except HTTPException:
        raise
    except IntegrityError as ie:
        logger.error(
            f"Integrity error while deleting tenant user | tenant_id={payload.tenant_id} user_id={payload.user_id}: {ie}"
        )
        raise HTTPException(
            status_code=409,
            detail="Tenant user deletion failed due to integrity constraint violation",
        )
    except Exception as exc:
        logger.exception(
            f"Unexpected error while deleting tenant user | tenant_id={payload.tenant_id} user_id={payload.user_id}: {exc}"
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/update/tenant", response_model=TenantUpdateResponse, status_code=status.HTTP_200_OK)
async def update_tenant_info(
    payload: TenantUpdateRequest,
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    Update tenant information including organization_name, contact_email, domain,
    requested_quotas, and usage_quota. Supports partial updates - only provided
    fields will be updated.
    """
    try:
        return await update_tenant(payload, db)
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


@router.get("/view/tenant", status_code=status.HTTP_200_OK)
async def view_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    View tenant details by tenant_id (human-readable tenant identifier).
    """
    try:
        result = await view_tenant_details(tenant_id, db)

        if not result:
            raise HTTPException(status_code=404, detail="Tenant not found")

        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Error viewing tenant details | tenant_id={tenant_id}: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")
    


@router.get("/view/user", status_code=status.HTTP_200_OK)
async def view_tenant_user(
    user_id: int,
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    View tenant user details by tenant_id and auth user_id.

    """
    try:
        result = await view_tenant_user_details(user_id, db)

        if not result:
            raise HTTPException(status_code=404, detail="Tenant user not found")

        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Error viewing tenant user details | user_id={user_id}: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/list/tenants", response_model=ListTenantsResponse, status_code=status.HTTP_200_OK)
async def list_tenants(
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    List all tenants with their details.
    Returns a list of all tenants registered in the system.
    """
    try:
        return await list_all_tenants(db)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Error listing tenants: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/list/users", response_model=ListUsersResponse, status_code=status.HTTP_200_OK)
async def list_users(
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    List all tenant users across all tenants.
    Returns a list of all users registered under any tenant.
    """
    try:
        return await list_all_users(db)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Error listing users: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")
