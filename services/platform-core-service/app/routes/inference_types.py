from fastapi import APIRouter

from ai4i_core.ppu import get_inference_types
from app.core.responses import success_response
from app.schemas.common import SuccessResponse
from app.schemas.inference_types import InferenceTypesResponse

router = APIRouter(
    prefix="/inference-types",
    tags=["Inference Types"],
)

_INFERENCE_TYPES: list = get_inference_types()


@router.get("", response_model=SuccessResponse[InferenceTypesResponse])
async def list_inference_types():
    return success_response({"inference_types": _INFERENCE_TYPES})
