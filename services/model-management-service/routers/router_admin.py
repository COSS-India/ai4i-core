from fastapi import HTTPException, status , APIRouter
from models.model_create import ModelCreateRequest
from models.model_update import ModelUpdateRequest
from models.service_create import ServiceCreateRequest
from models.service_update import ServiceUpdateRequest
from models.service_health import ServiceHeartbeatRequest
from db_operations import (
    save_model_to_db , 
    update_model , 
    delete_model_by_uuid , 
    save_service_to_db,
    update_service,
    delete_service_by_uuid,
    update_service_health
    )
from logger import logger

router_admin = APIRouter(prefix="/services/admin", tags=["Model Management"])


#################################################### Model apis ####################################################


@router_admin.post("/create/model", response_model=str)
async def create_model_request(payload: ModelCreateRequest):
    try:
        save_model_to_db(payload)

        logger.info(f"Model '{payload.name}' inserted successfully.")
        return f"Model '{payload.name}' (ID: {payload.modelId}) created successfully."

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while saving model to DB.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Model insert not successful"}
        )
    


@router_admin.patch("/update/model", response_model=str)
async def update_model_request(payload: ModelUpdateRequest):
    try:
        result = update_model(payload)

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
        result = delete_model_by_uuid(id)

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
async def create_service_request(payload: ServiceCreateRequest):

    try:
        save_service_to_db(payload)

        logger.info(f"Service '{payload.name}' inserted successfully.")
        return f"Service '{payload.name}' (ID: {payload.serviceId}) created successfully."

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while saving service to DB.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Service insert not successful"}
        )


@router_admin.patch("/update/service")
async def update_service_request(payload: ServiceUpdateRequest):
    
    try:
        result = update_service(payload)

        if result == 0:
            logger.warning(f"No DB record found for service {payload.serviceId}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found in database"
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
        result = delete_service_by_uuid(id)

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
        result = update_service_health(payload)

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
    

