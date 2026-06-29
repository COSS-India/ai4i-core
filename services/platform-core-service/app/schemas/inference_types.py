from typing import List

from pydantic import BaseModel


class InferenceTypeItem(BaseModel):
    name: str
    endpoint_pattern: str
    unit: str


class InferenceTypesResponse(BaseModel):
    inference_types: List[InferenceTypeItem]
