from fastapi import FastAPI, HTTPException, Request, status , APIRouter
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from models.model_create import ModelCreateRequest
from models.model_update import ModelUpdateRequest
from models.service_create import ServiceCreateRequest
from db_operations import (
    save_model_to_db , 
    update_model , 
    delete_model_by_uuid , 
    save_service_to_db
    )

from logger import logger

router_admin = APIRouter(prefix="/services/admin", tags=["Model Management"])


#################################################### Model Routers ####################################################


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
async def update_model_request(request: ModelUpdateRequest):
    try:
        result = update_model(request)

        if result == 0:
            logger.warning(f"No DB record found for model {request.modelId}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Model not found in database"
            )

        return f"Model '{request.modelId}' updated successfully."

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
    

#################################################### Service Routers ####################################################


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

