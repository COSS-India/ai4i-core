from fastapi import HTTPException, status , APIRouter , Depends , Query
from middleware.auth_provider import AuthProvider
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
from typing import List , Union, Optional
from models.type_enum import TaskTypeEnum


# Authentication is handled by Kong + Auth Service, no need for AuthProvider here
router_details = APIRouter(
    prefix="/services/details", 
    tags=["Model Management"],
    # dependencies=[Depends(AuthProvider)]
    )


#################################################### Model apis ####################################################


@router_details.post("/view_model", response_model=ModelViewResponse)
async def view_model_request(payload: ModelViewRequest):
    
    try: 
        data = await get_model_details(payload.modelId, version=payload.version)

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
async def list_models_request(
    task_type: Union[str, None] = Query(None, description="Filter by task type (asr, nmt, tts, etc.)"),
    include_deprecated: bool = Query(True, description="Include deprecated versions. Set to false to show only ACTIVE versions."),
    model_name: Optional[str] = Query(None, description="Filter by model name. Returns all versions of models matching this name.")
):
    try:
        if not task_type or task_type.lower() == "none":
            task_type_enum = None
        else:
            task_type_enum = TaskTypeEnum(task_type)

        data = await list_all_models(task_type_enum, include_deprecated=include_deprecated, model_name=model_name)
        if data is None:
            return []  # Return empty list instead of 404

        return data
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while listing model details from DB.")
        raise HTTPException(
            status_code=500,
            detail={"kind": "DBError", "message": "Error listing model details"}
        )
    

#################################################### Service apis ####################################################


@router_details.post("/view_service")
async def view_service_request(payload: ServiceViewRequest):
    # Note: response_model removed to allow returning dict with extra fields preserved
    
    try: 
        data = await get_service_details(payload.serviceId)

        if not data:
            raise HTTPException(status_code=404, detail="Service not found")
        # Return dict directly to preserve all fields including model_name in inferenceEndPoint
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
async def list_services_request(
    task_type: Union[str, None] = Query(None, description="Filter by task type (asr, nmt, tts, etc.)"),
    is_published: Optional[bool] = Query(None, description="Filter by publish status. True = published only, False = unpublished only, None = all services")
):
    try:
        if not task_type or task_type.lower() == "none":
            task_type_enum = None
        else:
            task_type_enum = TaskTypeEnum(task_type)

        data = await list_all_services(task_type_enum, is_published=is_published)

        if data is None:
            return []  # Return empty list instead of 404

        return data
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while listing service details from DB.")
        raise HTTPException(
            status_code=500,
            detail={"kind": "DBError", "message": "Error listing service details"}
        )
    