"""
Standard RESTful API router for Services - aligned with API Gateway paths.
Routes: /services (GET, POST, PATCH, DELETE), /services/{service_id} (POST for view),
/services/{service_id}/health (PATCH), /services/policies (GET for SMR)
"""
from fastapi import HTTPException, status, APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from middleware.auth_provider import AuthProvider
from models.service_list import ServiceListResponse
from models.service_policy import ServicePolicyUpdateRequest, ServicePolicyResponse, ServicePolicyListResponse
from models.service_create import ServiceCreateRequest
from models.service_update import ServiceUpdateRequest
from models.service_health import ServiceHeartbeatRequest
from db_operations import (
    get_model_details,
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
from db_connection import get_auth_db_session
from utils.permission_checker import require_permission, require_permission_dependency
from utils.request_helpers import get_user_id, validate_endpoint_or_raise
from logger import logger
from typing import List, Union, Optional
from models.type_enum import TaskTypeEnum


def _extract_validation_params(model_data: dict) -> dict:
    """Pull task_type, request_schema, triton_schema from model data."""
    task_type = (model_data.get("task") or {}).get("type")
    inference_ep = model_data.get("inferenceEndPoint") or {}
    schema = inference_ep.get("schema") or {}
    return {
        "task_type": task_type,
        "request_schema": schema.get("request"),
        "triton_schema": (schema.get("response") or {}).get("triton"),
    }


router_services = APIRouter(
    prefix="/services",
    tags=["Model Management"],
)


@router_services.get("", response_model=List[ServiceListResponse], dependencies=[Depends(AuthProvider)])
async def list_services(
    request: Request,
    task_type: Union[str, None] = Query(None, description="Filter by task type (asr, nmt, tts, etc.)"),
    is_published: Optional[bool] = Query(None, description="Filter by publish status. True = published only, False = unpublished only, None = all services"),
    created_by: Optional[str] = Query(None, description="Filter by user ID (string) who created the service."),
    db: AsyncSession = Depends(get_auth_db_session)
):
    """List all services - GET /services.
    
    Access: Any authenticated user role (ADMIN, MODERATOR, USER, GUEST)."""
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


@router_services.get(
    "/try-it-service-list",
    response_model=List[ServiceListResponse],
    summary="Public try-it service listing API",
    tags=["Model Management"],
)
async def list_services_try_it(
    task_type: str = Query(
        ...,
        description="Task type for try-out listing (currently only 'nmt' is supported).",
    ),
    db: AsyncSession = Depends(get_auth_db_session),
    ):
    """Public 'try it' services listing - GET /services/try-it-service-list.

    - No authentication required.
    - Currently supported only for `nmt` task type.
    - For any other task type, returns an error indicating try-it is not available.
    """
    try:
        if not task_type or task_type.lower() != TaskTypeEnum.nmt.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Try-it is not available in these services",
            )

        task_type_enum = TaskTypeEnum.nmt

        data = await list_all_services(task_type_enum, is_published=True, created_by=None)

        if data is None:
            return []

        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error while listing try-it service details from DB.")
        raise HTTPException(
            status_code=500,
            detail={
                "kind": "DBError",
                "message": "Error listing try-it service details",
                "error": str(e),
            },
        )

@router_services.get("/policies", response_model=ServicePolicyListResponse, include_in_schema=False)
async def list_services_policies(
    request: Request,
    task_type: Union[str, None] = Query(None, description="Filter by task type (asr, nmt, tts, etc.). Returns all services with their policies."),
    db: AsyncSession = Depends(get_auth_db_session)
):
    """List all services with their policies - GET /services/policies.
    
    Access: Any authenticated user role (ADMIN, MODERATOR, USER, GUEST)."""
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


@router_services.post("/{service_id:path}", dependencies=[Depends(AuthProvider)])
async def view_service(
    service_id: str,
    request: Request,
    db: AsyncSession = Depends(get_auth_db_session)
):
    """View service details by ID - POST /services/{service_id}. Requires 'service.read' (all authenticated roles, including USER and GUEST, for inference resolution)."""
    await require_permission("service.read", request, db)
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


@router_services.post("", response_model=str, dependencies=[Depends(AuthProvider), Depends(require_permission_dependency("service.create"))])
async def create_service(
    payload: ServiceCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_auth_db_session)
):
    """Create a new service - POST /services. Requires 'service.create' permission (ADMIN or MODERATOR only)."""
    
    try:
        model_data = await get_model_details(payload.modelId, version=payload.modelVersion)
        if not model_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Model with ID '{payload.modelId}' version '{payload.modelVersion}' not found. Cannot validate endpoint.",
            )

        params = _extract_validation_params(model_data)
        await validate_endpoint_or_raise(
            endpoint=payload.endpoint,
            api_key=payload.api_key,
            error_message="Service endpoint validation failed.",
            **params,
        )

        user_id = get_user_id(request)
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


@router_services.patch("", response_model=str, dependencies=[Depends(AuthProvider), Depends(require_permission_dependency("service.update"))])
async def update_service_endpoint(
    payload: ServiceUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_auth_db_session)
):
    """Update a service - PATCH /services. Requires appropriate permission (ADMIN or MODERATOR only).
    For publish/unpublish operations, requires 'model.publish' or 'model.unpublish'.
    For other updates, requires 'service.update'."""
    if payload.isPublished is not None:
        permission = "model.publish" if payload.isPublished else "model.unpublish"
        await require_permission(permission, request, db)
    
    try:
        if payload.endpoint:
            service_data = await get_service_details(payload.serviceId)
            if service_data:
                model_info = service_data.get("model") or {}
                params = _extract_validation_params(model_info)
                api_key = payload.api_key or service_data.get("api_key")
                await validate_endpoint_or_raise(
                    endpoint=payload.endpoint,
                    api_key=api_key,
                    error_message="Service endpoint validation failed.",
                    **params,
                )

        user_id = get_user_id(request)
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


@router_services.delete("/{service_id:path}", response_model=str, dependencies=[Depends(AuthProvider), Depends(require_permission_dependency("service.delete"))])
async def delete_service(
    service_id: str,
    request: Request,
    db: AsyncSession = Depends(get_auth_db_session)
):
    """Delete a service - DELETE /services/{service_id}. Requires 'service.delete' permission (ADMIN or MODERATOR only)."""
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


@router_services.patch("/{service_id:path}/health", dependencies=[Depends(AuthProvider)])
async def update_service_health_endpoint(service_id: str, payload: ServiceHeartbeatRequest, request: Request):
    """Update health status for a service - PATCH /services/{service_id}/health (service_id may contain slashes)"""
    try:
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


@router_services.post("/{service_id:path}/policy", response_model=ServicePolicyResponse, dependencies=[Depends(AuthProvider)], include_in_schema=False)
async def add_or_update_service_policy_endpoint(service_id: str, payload: ServicePolicyUpdateRequest, request: Request):
    """Add or update policy for a service - POST /services/{service_id}/policy (service_id may contain slashes)"""
    try:
        user_id = get_user_id(request)
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
