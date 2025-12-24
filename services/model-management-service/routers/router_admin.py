from fastapi import HTTPException, status , APIRouter
from models.model_create import ModelCreateRequest
from models.model_update import ModelUpdateRequest
from models.service_create import ServiceCreateRequest
from models.service_update import ServiceUpdateRequest
from models.service_health import ServiceHeartbeatRequest
from models.model_view import ModelViewRequest
from db_operations import (
    save_model_to_db , 
    update_model , 
    delete_model_by_uuid , 
    save_service_to_db,
    update_service,
    delete_service_by_uuid,
    update_service_health,
    publish_model,
    unpublish_model,
    create_model_version,
    get_model_versions,
    deprecate_model_version,
    get_services_by_model_version,
    get_services_using_deprecated_versions
)
from models.model_version import ModelVersionCreateRequest, ModelVersionStatusUpdateRequest
from services.service_version_service import ServiceVersionService
from services.version_service import VersionService
from db_connection import get_app_db_session
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, Query
from typing import Optional
from logger import logger

# Authentication is handled by Kong + Auth Service, no need for AuthProvider here
router_admin = APIRouter(
    prefix="/services/admin", 
    tags=["Model Management"]
)


#################################################### Model apis ####################################################


@router_admin.post("/create/model", response_model=str)
async def create_model_request(payload: ModelCreateRequest):
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
    


@router_admin.patch("/update/model", response_model=str)
async def update_model_request(payload: ModelUpdateRequest):
    try:
        result = await update_model(payload)

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


@router_admin.post("/publish/model", response_model=str)
async def publish_model_request(
    payload: ModelViewRequest,
    version: Optional[str] = Query(None, description="Specific version to publish. Defaults to latest active version.")
):
    
    try: 
        result = await publish_model(payload.modelId, version=version)

        if result == 0:
            raise HTTPException(status_code=404, detail="Model not found for publish")
        
        return f"Model '{payload.modelId}' version '{version}' published successfully."
    
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while updating model published status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Error updating model status as published"}
        )
    

@router_admin.post("/unpublish/model", response_model=str)
async def unpublish_model_request(
    payload: ModelViewRequest,
    version: Optional[str] = Query(None, description="Specific version to unpublish. Defaults to latest active version.")
):
    
    try: 
        result = await unpublish_model(payload.modelId, version=version)

        if result == 0:
            raise HTTPException(status_code=404, detail="Model not found for unpublish")
        
        return f"Model '{payload.modelId}' version '{version}' unpublished successfully."
    
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while updating model unpublished status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Error updating model status as unpublished"}
        )


@router_admin.post("/create/model/{model_id}/version", response_model=dict)
async def create_model_version_request(
    model_id: str,
    payload: ModelVersionCreateRequest,
    db: AsyncSession = Depends(get_app_db_session)
):
    """Create a new version under an existing model - Admin endpoint"""
    try:
        # Get base model data to use as template
        from db_operations import get_model_details
        from repositories.model_repository import ModelRepository
        
        base_model_data = await get_model_details(model_id)
        if not base_model_data:
            raise HTTPException(status_code=404, detail=f"Base model {model_id} not found")
        
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


@router_admin.patch("/deprecate/model/version", response_model=str)
async def deprecate_model_version_request(
    model_id: str = Query(..., alias="model_id"),
    version: str = Query(..., alias="version")
):
    """Mark a model version as deprecated - Admin endpoint"""
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


@router_admin.get("/model/{model_id}/versions", response_model=list)
async def get_model_versions_request(model_id: str):
    """List all versions of a model - Admin endpoint"""
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


@router_admin.get("/model/{model_id}/version/{version}/services", response_model=list)
async def get_services_by_version_request(model_id: str, version: str):
    """Find all services using a specific model version - Admin endpoint"""
    try:
        services = await get_services_by_model_version(model_id, version)
        return services
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while fetching services by version.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Error fetching services by version"}
        )


@router_admin.get("/model/{model_id}/deprecated-version-services", response_model=list)
async def get_deprecated_version_services_request(model_id: str):
    """Identify services using deprecated versions of a model - Admin endpoint"""
    try:
        services = await get_services_using_deprecated_versions(model_id)
        return services
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while fetching services using deprecated versions.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Error fetching services using deprecated versions"}
        )


@router_admin.patch("/update/service/version", response_model=str)
async def update_service_version_request(
    service_id: str = Query(..., alias="service_id"),
    new_version: str = Query(..., alias="new_version"),
    db: AsyncSession = Depends(get_app_db_session)
):
    """Switch a service to a different model version - Admin endpoint"""
    try:
        service_version_service = ServiceVersionService(db)
        user_id = None  # Could extract from auth context if needed
        await service_version_service.switch_service_version(service_id, new_version, user_id=user_id)
        logger.info(f"Service '{service_id}' switched to version '{new_version}' successfully.")
        return f"Service '{service_id}' switched to version '{new_version}' successfully."
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while switching service version.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Service version switch not successful"}
        )




#################################################### Service apis ####################################################


@router_admin.post("/create/service")
async def create_service_request(payload: ServiceCreateRequest):

    try:
        await save_service_to_db(payload)

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
        result = await update_service(payload)

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
    

