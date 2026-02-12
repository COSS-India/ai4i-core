"""
Standard RESTful API router for Services - aligned with API Gateway paths.
Routes: /services/ (GET), /services/{service_id} (POST for view), /services (POST, PATCH, DELETE),
/services/{service_id}/health (PATCH), /services/policies (GET for SMR)
"""
from fastapi import HTTPException, status, APIRouter, Depends, Query, Request
from middleware.auth_provider import AuthProvider
from models.service_list import ServiceListResponse
from models.service_policy import ServicePolicyUpdateRequest, ServicePolicyResponse, ServicePolicyListResponse
from models.service_create import ServiceCreateRequest
from models.service_update import ServiceUpdateRequest
from models.service_health import ServiceHeartbeatRequest
from db_operations import (
    get_service_details,
    list_all_services,
    get_service_policy,
    list_services_with_policies,
    save_service_to_db,
    update_service,
    delete_service_by_uuid,
    update_service_health,
    add_or_update_service_policy,
)
from logger import logger
from typing import List, Union, Optional
from models.type_enum import TaskTypeEnum


def get_user_id_from_request(request: Request) -> Optional[str]:
    """Extract user_id from request state (set by AuthProvider or Kong) as string."""
    user_id = getattr(request.state, 'user_id', None)
    return str(user_id) if user_id is not None else None


router_services = APIRouter(
    prefix="/services",
    tags=["Model Management"],
)

# Routes that require auth (added via route-level Depends)
# Routes without auth: list_services, list_services_policies (used by SMR, nmt, transliteration)


@router_services.get("", response_model=List[ServiceListResponse])
async def list_services(
    task_type: Union[str, None] = Query(None, description="Filter by task type (asr, nmt, tts, etc.)"),
    is_published: Optional[bool] = Query(None, description="Filter by publish status. True = published only, False = unpublished only, None = all services"),
    created_by: Optional[str] = Query(None, description="Filter by user ID (string) who created the service.")
):
    """List all services - GET /services/ or GET /services"""
    try:
        if not task_type or task_type.lower() == "none":
            task_type_enum = None
        else:
            task_type_enum = TaskTypeEnum(task_type)

        data = await list_all_services(task_type_enum, is_published=is_published, created_by=created_by)

        if data is None:
            return []

        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error while listing service details from DB.")
        raise HTTPException(
            status_code=500,
            detail={
                "kind": "DBError",
                "message": "Error listing service details",
                "error": str(e),
            }
        )


@router_services.get("/policies", response_model=ServicePolicyListResponse, include_in_schema=False)
async def list_services_policies(
    task_type: Union[str, None] = Query(None, description="Filter by task type (asr, nmt, tts, etc.). Returns all services with their policies.")
):
    """List all services with their policies - GET /services/policies (used by SMR)"""
    try:
        if not task_type or task_type.lower() == "none":
            task_type_enum = None
        else:
            task_type_enum = TaskTypeEnum(task_type)

        services_list = await list_services_with_policies(task_type_enum)
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


@router_services.post("/{service_id}", dependencies=[Depends(AuthProvider)])
async def view_service(service_id: str):
    """View service details by ID - POST /services/{service_id} (body can include serviceId for override)"""
    try:
        data = await get_service_details(service_id)
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


@router_services.post("", response_model=str, dependencies=[Depends(AuthProvider)])
async def create_service(payload: ServiceCreateRequest, request: Request):
    """Create a new service - POST /services"""
    try:
        user_id = get_user_id_from_request(request)
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


@router_services.patch("", response_model=str, dependencies=[Depends(AuthProvider)])
async def update_service_endpoint(payload: ServiceUpdateRequest, request: Request):
    """Update a service - PATCH /services"""
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


@router_services.delete("/{service_id}", response_model=str, dependencies=[Depends(AuthProvider)])
async def delete_service(service_id: str):
    """Delete a service - DELETE /services/{service_id}"""
    try:
        result = await delete_service_by_uuid(service_id)

        if result == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"kind": "NotFound", "message": f"Service with id '{service_id}' not found"}
            )

        return f"Service '{service_id}' deleted successfully."

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while deleting service from DB.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Service delete not successful"}
        )


@router_services.patch("/{service_id}/health", dependencies=[Depends(AuthProvider)])
async def update_service_health_endpoint(service_id: str, payload: ServiceHeartbeatRequest, request: Request):
    """Update health status for a service - PATCH /services/{service_id}/health"""
    try:
        # Override serviceId from path
        merged_payload = ServiceHeartbeatRequest(serviceId=service_id, status=payload.status)
        result = await update_service_health(merged_payload)

        if result == 0:
            logger.warning(f"No DB record found for service {service_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found"
            )

        return f"Service '{service_id}' health status updated successfully."

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while updating health status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Service health status update not successful"}
        )


@router_services.post("/{service_id}/policy", response_model=ServicePolicyResponse, dependencies=[Depends(AuthProvider)], include_in_schema=False)
async def add_or_update_service_policy_endpoint(service_id: str, payload: ServicePolicyUpdateRequest, request: Request):
    """Add or update policy for a service - POST /services/{service_id}/policy"""
    try:
        user_id = get_user_id_from_request(request)
        result = await add_or_update_service_policy(
            service_id=service_id,
            policy_data=payload.policy,
            updated_by=user_id,
        )
        return ServicePolicyResponse(**result)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while adding/updating service policy.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Service policy add/update not successful"}
        )
