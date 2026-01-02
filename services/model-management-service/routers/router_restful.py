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
)
from logger import logger
from typing import List, Union, Optional
from models.type_enum import TaskTypeEnum

router_restful = APIRouter(
    prefix="/models",
    tags=["Model Management RESTful"],
    dependencies=[Depends(AuthProvider)]
)


@router_restful.get("", response_model=List[ModelViewResponse])
async def list_models_restful(
    task_type: Union[str, None] = Query(None, description="Filter by task type (asr, nmt, tts, etc.)"),
    include_deprecated: bool = Query(True, description="Include deprecated versions. Set to false to show only ACTIVE versions.")
):
    """List all models - RESTful endpoint"""
    try:
        if not task_type or task_type.lower() == "none":
            task_type_enum = None
        else:
            task_type_enum = TaskTypeEnum(task_type)

        data = await list_all_models(task_type_enum, include_deprecated=include_deprecated)
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
async def get_model_by_id_restful(model_id: str, version: Optional[str] = Query(None, description="Optional version to get specific version")):
    """Get model by ID - RESTful endpoint. If version is provided, returns that specific version. Otherwise returns the first matching model."""
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


