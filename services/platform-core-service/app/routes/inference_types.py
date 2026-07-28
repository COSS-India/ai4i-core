from fastapi import APIRouter

from app.core.responses import success_response
from app.core.task_type_policy import get_enabled_inference_types
from app.schemas.common import SuccessResponse
from app.schemas.inference_types import InferenceTypesResponse

router = APIRouter(
    prefix="/inference-types",
    tags=["Inference Types"],
)


@router.get("", response_model=SuccessResponse[InferenceTypesResponse])
async def list_inference_types():
    # Only the task types enabled for this deployment (ENABLED_TASK_TYPES). This
    # is the single list the frontend builds its catalog from.
    return success_response({"inference_types": get_enabled_inference_types()})
