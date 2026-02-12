from fastapi import HTTPException, status , APIRouter , Depends , Query
from middleware.auth_provider import AuthProvider
from models.model_view import ModelViewRequest , ModelViewResponse
from models.service_view import ServiceViewRequest , ServiceViewResponse
from models.service_list import ServiceListResponse
from models.service_policy import ServicePolicyRequest, ServicePolicyResponse, ServicePolicyListResponse
from db_operations import (
    get_model_details , 
    list_all_models , 
    get_service_details,
    list_all_services,
    get_service_policy,
    list_services_with_policies
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
    model_name: Optional[str] = Query(None, description="Filter by model name. Returns all versions of models matching this name."),
    created_by: Optional[str] = Query(None, description="Filter by user ID (string) who created the model.")
):
    try:
        if not task_type or task_type.lower() == "none":
            task_type_enum = None
        else:
            task_type_enum = TaskTypeEnum(task_type)

        data = await list_all_models(task_type_enum, include_deprecated=include_deprecated, model_name=model_name, created_by=created_by)
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
    is_published: Optional[bool] = Query(None, description="Filter by publish status. True = published only, False = unpublished only, None = all services"),
    created_by: Optional[str] = Query(None, description="Filter by user ID (string) who created the service.")
):
    try:
        if not task_type or task_type.lower() == "none":
            task_type_enum = None
        else:
            task_type_enum = TaskTypeEnum(task_type)

        data = await list_all_services(task_type_enum, is_published=is_published, created_by=created_by)

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


#################################################### Policy apis ####################################################


@router_details.post("/get/service/policy", response_model=ServicePolicyResponse)
async def get_service_policy_request(payload: ServiceViewRequest):
    """
    Get policy for a specific service by service_id.
    
    Returns the service ID and its policy data (if set), or None if no policy is configured.
    """
    try:
        data = await get_service_policy(payload.serviceId)
        
        if not data:
            raise HTTPException(status_code=404, detail="Service not found")
        return data
        
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while fetching service policy from DB.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Error fetching service policy"}
        )


@router_details.get("/list/services/policies", response_model=ServicePolicyListResponse)
async def list_services_policies_request(
    task_type: Union[str, None] = Query(None, description="Filter by task type (asr, nmt, tts, etc.). Returns all services with their policies for the specified task type.")
):
    """
    List all services with their policies, optionally filtered by task_type.
    
    When task_type is provided (e.g., "nmt", "transliteration"), returns all service IDs
    along with their policy details for that task type.
    
    When service_id is needed, use /get/service/policy endpoint.
    """
    try:
        if not task_type or task_type.lower() == "none":
            task_type_enum = None
        else:
            task_type_enum = TaskTypeEnum(task_type)
        
        services_list = await list_services_with_policies(task_type_enum)
        
        # Convert to ServicePolicyResponse objects
        services_with_policies = [
            ServicePolicyResponse(**service) for service in services_list
        ]
        
        return ServicePolicyListResponse(services=services_with_policies)
        
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while listing services with policies from DB.")
        raise HTTPException(
            status_code=500,
            detail={"kind": "DBError", "message": "Error listing services with policies"}
        )
    