from fastapi import HTTPException, status , APIRouter
from models.model_view import ModelViewRequest , ModelViewResponse
from models.service_view import ServiceViewRequest , ServiceViewResponse
from models.service_list import ServiceListResponse
from db_operations import (
    get_model_details , 
    list_all_models , 
    get_service_details,
    list_all_services
)
from logger import logger
from typing import List


router_details = APIRouter(prefix="/services/details", tags=["Model Management"])


#################################################### Model apis ####################################################


@router_details.post("/view_model", response_model=ModelViewResponse)
async def view_model_request(payload: ModelViewRequest):
    
    try: 
        data = get_model_details(payload.modelId)

        if not data:
            raise HTTPException(status_code=404, detail="Model not found")
        return data
    
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while fetching model details from DB.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Error fetching model details"}
        )
    


@router_details.get("/list_models" , response_model=List[ModelViewResponse])
async def list_models_request():
    try:
        data = list_all_models()

        if not data:
            return []

        return data

    except Exception:
        logger.exception("Error while listing model details from DB.")
        raise HTTPException(
            status_code=500,
            detail={"kind": "DBError", "message": "Error listing model details"}
        )
    

#################################################### Service apis ####################################################


@router_details.post("/view_service", response_model=ServiceViewResponse)
async def view_service_request(payload: ServiceViewRequest):
    
    try: 
        data = get_service_details(payload.serviceId)

        if not data:
            raise HTTPException(status_code=404, detail="Service not found")
        return data
    
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while fetching service details from DB.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Error fetching service details"}
        )
    

@router_details.get("/list_services" , response_model=List[ServiceListResponse])
async def list_services_request():
    try:
        data = list_all_services()

        if not data:
            return []

        return data

    except Exception:
        logger.exception("Error while listing service details from DB.")
        raise HTTPException(
            status_code=500,
            detail={"kind": "DBError", "message": "Error listing service details"}
        )
    