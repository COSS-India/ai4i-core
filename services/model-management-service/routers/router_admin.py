from fastapi import HTTPException, status, APIRouter, Depends, Request
from typing import Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.model_create import ModelCreateRequest
from models.model_update import ModelUpdateRequest
from models.service_create import ServiceCreateRequest
from models.service_update import ServiceUpdateRequest
from models.service_health import ServiceHeartbeatRequest
from models.service_policy import ServicePolicyRequest, ServicePolicyResponse
from models.db_models import Service
from db_operations import (
    save_model_to_db , 
    update_model , 
    delete_model_by_uuid , 
    save_service_to_db,
    update_service,
    delete_service_by_uuid,
    update_service_health,
    add_or_update_service_policy,
    AppDatabase
    )
from middleware.auth_provider import AuthProvider
from logger import logger


def get_user_id_from_request(request: Request) -> Optional[str]:
    """Extract user_id from request state (set by AuthProvider or Kong) as string."""
    user_id = getattr(request.state, 'user_id', None)
    return str(user_id) if user_id is not None else None


router_admin = APIRouter(
    prefix="/services/admin", 
    tags=["Model Management"],
    dependencies=[Depends(AuthProvider)]
)


#################################################### Model apis ####################################################


@router_admin.post("/create/model", response_model=str)
async def create_model_request(payload: ModelCreateRequest, request: Request):
    try:
        user_id = get_user_id_from_request(request)
        model_id = await save_model_to_db(payload, created_by=user_id)

        logger.info(f"Model '{payload.name}' inserted successfully by user {user_id}.")
        return f"Model '{payload.name}' (ID: {model_id}) created successfully."

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while saving model to DB.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Model insert not successful"}
        )
    


@router_admin.patch("/update/model", response_model=str)
async def update_model_request(payload: ModelUpdateRequest, request: Request):
    try:
        user_id = get_user_id_from_request(request)
        # Log the incoming payload to debug
        logger.info(f"Received update request - modelId: {payload.modelId}, version: {payload.version}, versionStatus: {payload.versionStatus}, by user {user_id}")
        result = await update_model(payload, updated_by=user_id)

        if result == 0:
            logger.warning(f"No DB record found for model {payload.modelId}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Model not found in database"
            )

        return f"Model '{payload.modelId}' updated successfully."

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while updating model in DB.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Model update not successful"}
        )


@router_admin.delete("/delete/model", response_model=str)
async def delete_model_request(id: str):
    try:
        result = await delete_model_by_uuid(id)

        if result == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"kind": "NotFound", "message": f"Model with id '{id}' not found"}
            )

        return f"Model '{id}' deleted successfully."

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while deleting model from DB.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Model delete not successful"}
        )


#################################################### Service apis ####################################################


@router_admin.post("/create/service")
async def create_service_request(payload: ServiceCreateRequest, request: Request):
    try:
        user_id = get_user_id_from_request(request)
        # service_id is now auto-generated from hash of (model_name, model_version, service_name)
        service_id = await save_service_to_db(payload, created_by=user_id)

        logger.info(f"Service '{payload.name}' inserted successfully by user {user_id}.")
        return f"Service '{payload.name}' (ID: {service_id}) created successfully."

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while saving service to DB.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Service insert not successful"}
        )


@router_admin.patch("/update/service")
async def update_service_request(payload: ServiceUpdateRequest, request: Request):
    try:
        user_id = get_user_id_from_request(request)
        result = await update_service(payload, updated_by=user_id)

        if result == 0:
            logger.warning(f"No DB record found for service {payload.serviceId}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found in database"
            )
        
        if result == -1:
            logger.warning(f"No valid update fields provided for service {payload.serviceId}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid update fields provided. Valid fields: serviceDescription, hardwareDescription, endpoint, api_key, healthStatus, benchmarks, isPublished. Note: name, modelId, modelVersion are not updatable."
            )

        return f"Service '{payload.serviceId}' updated successfully."

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while updating service in DB.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Service update not successful"}
        )


@router_admin.delete("/delete/service", response_model=str)
async def delete_model_request(id: str):
    try:
        result = await delete_service_by_uuid(id)

        if result == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"kind": "NotFound", "message": f"Service with id '{id}' not found"}
            )

        return f"Service '{id}' deleted successfully."

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while deleting model from DB.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Service delete not successful"}
        )
    

@router_admin.patch("/health")
async def update_service_health_request(payload: ServiceHeartbeatRequest):
    try:
        result = await update_service_health(payload)

        if result == 0:
            logger.warning(f"No DB record found for service {payload.serviceId}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found in database"
            )

        return f"Service '{payload.serviceId}' health status updated successfully."

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while updating health status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Service health status update not successful"}
        )


#################################################### Policy apis ####################################################


@router_admin.post("/add/service/policy", response_model=ServicePolicyResponse)
async def add_or_update_service_policy_request(payload: ServicePolicyRequest, request: Request):
    """
    Add or update policy for a service.
    
    This endpoint handles both operations:
    - Adding a new policy if the service doesn't have one (policy is null)
    - Updating an existing policy if the service already has one
    
    Policy data includes:
    - latency: low, medium, or high
    - cost: tier_1, tier_2, or tier_3
    - accuracy: sensitive or standard
    
    The policy is stored in the database and will be used for smart routing decisions.
    
    Returns:
        ServicePolicyResponse with serviceId and policy data
    """
    try:
        user_id = get_user_id_from_request(request)
        
        # Check if service exists and has existing policy to determine operation type
        db: AsyncSession = AppDatabase()
        is_update = False
        try:
            result = await db.execute(select(Service).where(Service.service_id == payload.serviceId))
            service = result.scalars().first()
            if not service:
                raise HTTPException(status_code=404, detail=f"Service with ID '{payload.serviceId}' not found")
            is_update = service.policy is not None
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Error checking existing policy: {e}")
        finally:
            await db.close()
        
        result = await add_or_update_service_policy(
            service_id=payload.serviceId,
            policy_data=payload.policy,
            updated_by=user_id
        )
        
        # Log appropriate message based on operation
        operation = "updated" if is_update else "added"
        logger.info(f"Policy {operation} for service '{payload.serviceId}' by user {user_id}.")
        
        return ServicePolicyResponse(**result)
        
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while adding/updating service policy.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Service policy add/update not successful"}
        )
