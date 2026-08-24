from fastapi import APIRouter

from ai4i_core.ppu import get_inference_types
from app.schemas.inference_types import InferenceTypesResponse, ListInferenceTypesResponse

router = APIRouter(
    prefix="/inference-types",
    tags=["Inference Types"],
)

_INFERENCE_TYPES: list = get_inference_types()


@router.get("")
async def list_inference_types() -> ListInferenceTypesResponse:
    """List all supported inference types with their pricing unit."""
    return ListInferenceTypesResponse(
        success=True, data=InferenceTypesResponse(inference_types=_INFERENCE_TYPES)
    )
