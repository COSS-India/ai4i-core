"""
Standard RESTful API router for Models - aligned with API Gateway paths.
Routes: /models (GET, POST, PATCH), /models/{model_id} (GET, POST), /models/{model_id} (DELETE)
"""
from fastapi import HTTPException, status, APIRouter, Depends, Query, Request, Body
from middleware.auth_provider import AuthProvider
from models.model_view import ModelViewResponse, ModelViewRequestWithVersion
from models.model_create import ModelCreateRequest
from models.model_update import ModelUpdateRequest
from db_operations import (
    get_model_details,
    list_all_models,
    save_model_to_db,
    update_model,
    delete_model_by_uuid,
)
from logger import logger
from typing import List, Union, Optional
from models.type_enum import TaskTypeEnum


def get_user_id_from_request(request: Request) -> Optional[str]:
    """Extract user_id from request state (set by AuthProvider or Kong) as string."""
    user_id = getattr(request.state, 'user_id', None)
    return str(user_id) if user_id is not None else None


router_models = APIRouter(
    prefix="/models",
    tags=["Model Management"],
    dependencies=[Depends(AuthProvider)]
)


@router_models.get("", response_model=List[ModelViewResponse])
async def list_models(
    task_type: Union[str, None] = Query(None, description="Filter by task type (asr, nmt, tts, etc.)"),
    include_deprecated: bool = Query(True, description="Include deprecated versions. Set to false to show only ACTIVE versions."),
    model_name: Optional[str] = Query(None, description="Filter by model name. Returns all versions of models matching this name."),
    created_by: Optional[str] = Query(None, description="Filter by user ID (string) who created the model.")
):
    """List all models - GET /models"""
    try:
        if not task_type or task_type.lower() == "none":
            task_type_enum = None
        else:
            task_type_enum = TaskTypeEnum(task_type)

        data = await list_all_models(task_type_enum, include_deprecated=include_deprecated, model_name=model_name, created_by=created_by)
        if data is None:
            return []

        return data
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while listing model details from DB.")
        raise HTTPException(
            status_code=500,
            detail={"kind": "DBError", "message": "Error listing model details"}
        )


@router_models.get("/{model_id:path}", response_model=ModelViewResponse)
async def get_model_by_id(
    model_id: str,
    version: Optional[str] = Query(None, description="Optional version to get specific version")
):
    """Get model by ID - GET /models/{model_id}"""
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


@router_models.post("/{model_id:path}", response_model=ModelViewResponse)
async def view_model_by_id(
    model_id: str,
    payload: Optional[ModelViewRequestWithVersion] = Body(None, description="Request body with optional version")
):
    """Get model by ID with optional version in body - POST /models/{model_id}"""
    try:
        version = payload.version if payload else None
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


@router_models.post("", response_model=str)
async def create_model(payload: ModelCreateRequest, request: Request):
    """Create a new model - POST /models"""
    try:
        user_id = get_user_id_from_request(request)
        model_id = await save_model_to_db(payload, created_by=user_id)
        logger.info(f"Model '{payload.name}' inserted successfully by user {user_id}.")
        return f"Model '{payload.name}' (ID: {model_id}) created successfully."
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while saving model to DB.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Model insert not successful"}
        )


@router_models.patch("", response_model=str)
async def update_model_endpoint(payload: ModelUpdateRequest, request: Request):
    """Update a model - PATCH /models"""
    try:
        user_id = get_user_id_from_request(request)
        result = await update_model(payload, updated_by=user_id)

        if result == 0:
            logger.warning(f"No DB record found for model {payload.modelId}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Model not found in database"
            )

        logger.info(f"Model '{payload.modelId}' updated successfully by user {user_id}.")
        return f"Model '{payload.modelId}' updated successfully."

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while updating model in DB.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Model update not successful"}
        )


@router_models.delete("/{model_id:path}", response_model=str)
async def delete_model(model_id: str):
    """Delete a model by ID - DELETE /models/{model_id}"""
    try:
        result = await delete_model_by_uuid(model_id)

        if result == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"kind": "NotFound", "message": f"Model with id '{model_id}' not found"}
            )

        return f"Model '{model_id}' deleted successfully."

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while deleting model from DB.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Model delete not successful"}
        )
