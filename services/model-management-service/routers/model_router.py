from fastapi import FastAPI, HTTPException, Request, status , APIRouter
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from models.create_model import ModelCreateRequest
from db_operations import save_model_to_db
from logger import logger

model_router = APIRouter(prefix="/services/admin", tags=["Model Management"])



# -----------------------------
# Routes
# -----------------------------

@model_router.post("/create/model", response_model=str)
async def create_model(payload: ModelCreateRequest):
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
    
