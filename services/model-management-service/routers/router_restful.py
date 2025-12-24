"""
RESTful API router for Model Management Service
Provides RESTful endpoints that match frontend expectations
"""
from fastapi import HTTPException, status, APIRouter, Depends, Query
from middleware.auth_provider import AuthProvider
from models.model_view import ModelViewRequest, ModelViewResponse
from models.model_create import ModelCreateRequest
from models.model_update import ModelUpdateRequest
from db_operations import (
    get_model_details,
    list_all_models,
    save_model_to_db,
    update_model,
    publish_model,
    unpublish_model,
    create_model_version,
    get_model_versions,
    deprecate_model_version,
    get_services_by_model_version,
    get_services_using_deprecated_versions
)
from models.model_version import (
    ModelVersionCreateRequest,
    ModelVersionListResponse,
    ModelVersionStatusUpdateRequest
)
from middleware.permissions import ModeratorRequired
from services.service_version_service import ServiceVersionService
from services.version_service import VersionService
from db_connection import get_app_db_session
from sqlalchemy.ext.asyncio import AsyncSession
from logger import logger
from typing import List, Union, Optional
from models.type_enum import TaskTypeEnum
from pydantic import BaseModel

router_restful = APIRouter(
    prefix="/models",
    tags=["Model Management RESTful"],
    dependencies=[Depends(AuthProvider)]
)

# Service version router
router_services_restful = APIRouter(
    prefix="/services",
    tags=["Service Management RESTful"],
    dependencies=[Depends(AuthProvider)]
)


class ServiceVersionSwitchRequest(BaseModel):
    """Request model for switching service version"""
    version: str


@router_restful.get("", response_model=List[ModelViewResponse])
async def list_models_restful(
    task_type: Union[str, None] = Query(None),
    version_status: Optional[str] = Query(None, description="Filter by version status: 'active' or 'deprecated'")
):
    """List all models - RESTful endpoint"""
    try:
        if not task_type or task_type.lower() == "none":
            task_type_enum = None
        else:
            task_type_enum = TaskTypeEnum(task_type)

        data = await list_all_models(task_type_enum, version_status=version_status)
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


@router_restful.get("/{model_id}", response_model=ModelViewResponse)
async def get_model_by_id_restful(
    model_id: str,
    version: Optional[str] = Query(None, description="Specific version to retrieve. Defaults to latest active version.")
):
    """Get model by ID - RESTful endpoint"""
    try:
        data = await get_model_details(model_id, version=version)
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


@router_restful.post("", response_model=str)
async def create_model_restful(payload: ModelCreateRequest):
    """Create a new model - RESTful endpoint"""
    try:
        await save_model_to_db(payload)
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


@router_restful.patch("", response_model=str)
async def update_model_restful(payload: ModelUpdateRequest):
    """Update a model - RESTful endpoint"""
    try:
        await update_model(payload)
        logger.info(f"Model '{payload.modelId}' updated successfully.")
        return f"Model '{payload.modelId}' updated successfully."
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while updating model in DB.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Model update not successful"}
        )


@router_restful.post("/publish", response_model=str)
async def publish_model_restful(
    model_id: str = Query(..., alias="model_id"),
    version: Optional[str] = Query(None, description="Specific version to publish. Defaults to latest active version.")
):
    """Publish a model - RESTful endpoint"""
    try:
        await publish_model(model_id, version=version)
        logger.info(f"Model '{model_id}' version '{version}' published successfully.")
        return f"Model '{model_id}' version '{version}' published successfully."
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while publishing model.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Model publish not successful"}
        )


@router_restful.post("/unpublish", response_model=str)
async def unpublish_model_restful(
    model_id: str = Query(..., alias="model_id"),
    version: Optional[str] = Query(None, description="Specific version to unpublish. Defaults to latest active version.")
):
    """Unpublish a model - RESTful endpoint"""
    try:
        await unpublish_model(model_id, version=version)
        logger.info(f"Model '{model_id}' version '{version}' unpublished successfully.")
        return f"Model '{model_id}' version '{version}' unpublished successfully."
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while unpublishing model.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Model unpublish not successful"}
        )


@router_restful.get("/{model_id}/versions", response_model=List[dict])
async def list_model_versions_restful(
    model_id: str,
    auth_context: dict = ModeratorRequired
):
    """List all versions of a model - RESTful endpoint"""
    try:
        versions = await get_model_versions(model_id)
        return versions
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while listing model versions.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Error listing model versions"}
        )


@router_restful.post("/{model_id}/versions", response_model=dict)
async def create_model_version_restful(
    model_id: str,
    payload: ModelVersionCreateRequest,
    auth_context: dict = ModeratorRequired,
    db: AsyncSession = Depends(get_app_db_session)
):
    """Create a new version under an existing model - RESTful endpoint"""
    try:
        # Get base model data to use as template
        base_model_data = await get_model_details(model_id)
        if not base_model_data:
            raise HTTPException(status_code=404, detail=f"Base model {model_id} not found")
        
        # Convert to dict format for template
        from repositories.model_repository import ModelRepository
        repo = ModelRepository(db)
        base_model = await repo.find_by_model_id(model_id)
        if not base_model:
            raise HTTPException(status_code=404, detail=f"Base model {model_id} not found")
        
        base_data = {
            "submitted_on": base_model.submitted_on,
            "name": base_model.name,
            "description": base_model.description,
            "ref_url": base_model.ref_url,
            "task": base_model.task,
            "languages": base_model.languages,
            "license": base_model.license,
            "domain": base_model.domain,
            "inference_endpoint": base_model.inference_endpoint,
            "benchmarks": base_model.benchmarks,
            "submitter": base_model.submitter,
        }
        
        result = await create_model_version(model_id, payload, base_data)
        logger.info(f"Model version '{model_id}' v{payload.version} created successfully.")
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while creating model version.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Model version creation not successful"}
        )


@router_restful.patch("/{model_id}/versions/{version}/deprecate", response_model=str)
async def deprecate_model_version_restful(
    model_id: str,
    version: str,
    auth_context: dict = ModeratorRequired
):
    """Mark a model version as deprecated - RESTful endpoint"""
    try:
        await deprecate_model_version(model_id, version)
        logger.info(f"Model '{model_id}' version '{version}' deprecated successfully.")
        return f"Model '{model_id}' version '{version}' deprecated successfully."
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while deprecating model version.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Model version deprecation not successful"}
        )


#################################################### Service Version Endpoints ####################################################


@router_services_restful.patch("/{service_id}/version", response_model=dict)
async def switch_service_version_restful(
    service_id: str,
    payload: ServiceVersionSwitchRequest,
    auth_context: dict = ModeratorRequired,
    db: AsyncSession = Depends(get_app_db_session)
):
    """Switch a service to a different model version - RESTful endpoint"""
    try:
        service_version_service = ServiceVersionService(db)
        user_id = auth_context.get("user_id") if auth_context else None
        await service_version_service.switch_service_version(
            service_id, 
            payload.version, 
            user_id=user_id
        )
        logger.info(f"Service '{service_id}' switched to version '{payload.version}' successfully.")
        return {
            "message": f"Service '{service_id}' switched to version '{payload.version}' successfully.",
            "serviceId": service_id,
            "version": payload.version
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while switching service version.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Service version switch not successful"}
        )


@router_services_restful.get("/{service_id}/available-versions", response_model=dict)
async def get_available_versions_for_service_restful(
    service_id: str,
    auth_context: dict = ModeratorRequired,
    db: AsyncSession = Depends(get_app_db_session)
):
    """Get available versions for a service - RESTful endpoint"""
    try:
        service_version_service = ServiceVersionService(db)
        versions = await service_version_service.get_available_versions_for_service(service_id)
        return {
            "serviceId": service_id,
            "availableVersions": versions
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while fetching available versions for service.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Error fetching available versions"}
        )



