from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from db_connection import get_tenant_db_session , get_auth_db_session
from models.tenant_create import TenantRegisterRequest, TenantRegisterResponse
from models.user_create import UserRegisterRequest , UserRegisterResponse
from tenant_service import create_new_tenant , register_user

from logger import logger
from middleware.auth_provider import AuthProvider


router = APIRouter(
    prefix="/admin", 
    tags=["Tenants registeration"],
    # dependencies=[Depends(AuthProvider)]
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
        raise HTTPException(status_code=409, detail="User already exists")
    except ValueError as ve:
        logger.error(f"Validation error during user registration: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        logger.exception(f"Unexpected error during user registration: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")


