from typing import List

from pydantic import BaseModel

from app.schemas.common import SuccessResponse


class InferenceTypeItem(BaseModel):
    name: str
    endpoint_pattern: str
    unit: str
    pricing: str


class InferenceTypesResponse(BaseModel):
    inference_types: List[InferenceTypeItem]


# ── Route response envelope — ``{"success": true, "data": ...}`` ──


class ListInferenceTypesResponse(SuccessResponse):
    """GET /inference-types"""

    data: InferenceTypesResponse
