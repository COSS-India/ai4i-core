from fastapi import FastAPI, HTTPException, Request, status , APIRouter
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from models.model_create import ModelCreateRequest
from models.model_update import ModelUpdateRequest
from db_operations import save_model_to_db , update_model
from logger import logger

model_router = APIRouter(prefix="/services/admin", tags=["Model Management"])



@model_router.post("/create/model", response_model=str)
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
    


@model_router.patch("/update/model", response_model=str)
async def update_model_request(request: ModelUpdateRequest):
    try:
        result = update_model(request)

        # logger.info(f"Model '{request.modelId}' updated successfully.")
        return f"Model '{request.modelId}' updated successfully."

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while updating model in DB.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Model update not successful"}
        )
