from fastapi import HTTPException, status , APIRouter
from models.model_view import ModelViewRequest , ModelViewResponse
from db_operations import get_model_details , list_all_models
from logger import logger
from typing import List


router_details = APIRouter(prefix="/services/details", tags=["Model Management"])



@router_details.post("/view_model", response_model=ModelViewResponse)
async def view_model(payload: ModelViewRequest):
    
    try: 
        data = get_model_details(payload.modelId)

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
async def list_models():
    try:
        data = list_all_models()

        if not data:
            return []  # Return empty list, not 404

        return data

    except Exception:
        logger.exception("Error while listing model details from DB.")
        raise HTTPException(
            status_code=500,
            detail={"kind": "DBError", "message": "Error listing model details"}
        )