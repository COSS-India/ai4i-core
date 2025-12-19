from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from db_connection import get_tenant_db_session
from models.tenant_create import TenantRegisterRequest, TenantRegisterResponse
from models.service_create import ServiceCreateRequest , ListServicesResponse , ServiceResponse
from models.services_update import ServiceUpdateRequest , ServiceUpdateResponse
from tenant_service import create_new_tenant, create_service , update_service , list_service

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
    


@router.post("/register/services", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED)
async def register_service_request(
    payload: ServiceCreateRequest,
    db: AsyncSession = Depends(get_tenant_db_session),
):  
    try:
        response = await create_service(payload, db)
        logger.info(f"Service created successfully. Service: {payload.service_name}")
        return response
    
    except HTTPException:
        raise
    except IntegrityError as ie:
        logger.error(f"Integrity error during service creation: {ie}")
        raise HTTPException(status_code=409, detail="Service with this name or ID already exists")
    except ValueError as ve:
        logger.error(f"Value error during service creation: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        logger.exception(f"Error creating service pricing: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")



@router.post("/update/services", response_model=ServiceUpdateResponse, status_code=status.HTTP_201_CREATED)
async def update_service_request(
    payload: ServiceUpdateRequest,
    db: AsyncSession = Depends(get_tenant_db_session),
):
    try:
        result = await update_service(payload, db)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Error updating service pricing: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/list/services", response_model=ListServicesResponse, status_code=status.HTTP_200_OK)
async def list_services_request(db: AsyncSession = Depends(get_tenant_db_session)):
    try:
        result = await list_service(db)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Error listing services: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")



