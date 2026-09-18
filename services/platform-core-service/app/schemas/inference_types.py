from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import SuccessResponse


class InferenceTypeItem(BaseModel):
    """Response shape for one inference type.

    Deliberately keeps the scalar ``endpoint_pattern`` + optional
    ``endpoint_aliases`` pair that the YAML catalogue exposed, even though the
    table stores a single ``endpoint_patterns`` array. Both consumers validate
    against this shape and would break on an array:
      * ``frontend/simple-ui/src/services/inferenceTypesService.ts`` declares
        ``endpoint_pattern: z.string()`` as required — zod rejects, it does not
        degrade.
      * ``auth-service/app/routes/validation.py`` reads ``endpoint_pattern`` and
        ``endpoint_aliases`` as separate fields when building its path table.
    Collapsing the two into one array is a phase 2 change that must land with
    the frontend.
    """

    id: int
    name: str
    endpoint_pattern: str
    endpoint_aliases: Optional[List[str]] = None
    unit: str
    pricing: str


class InferenceTypesResponse(BaseModel):
    inference_types: List[InferenceTypeItem]


def _normalize_patterns(v: List[str]) -> List[str]:
    cleaned = [p.strip() for p in v if p and p.strip()]
    if not cleaned:
        raise ValueError("endpoint_patterns must contain at least one non-empty path")
    if len(set(cleaned)) != len(cleaned):
        raise ValueError("endpoint_patterns must not contain duplicates")
    return cleaned


class InferenceTypeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    endpoint_patterns: List[str] = Field(..., min_length=1)
    unit: str = Field(..., min_length=1, max_length=64)
    pricing: str = Field(..., min_length=1, max_length=64)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        # The catalogue is keyed case-insensitively everywhere it is read
        # (cache keys, the billing join, tier_service's lower() filters).
        return v.strip().lower()

    @field_validator("endpoint_patterns")
    @classmethod
    def validate_patterns(cls, v: List[str]) -> List[str]:
        return _normalize_patterns(v)


class InferenceTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    endpoint_patterns: Optional[List[str]] = None
    unit: Optional[str] = Field(None, min_length=1, max_length=64)
    pricing: Optional[str] = Field(None, min_length=1, max_length=64)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().lower() if v is not None else None

    @field_validator("endpoint_patterns")
    @classmethod
    def validate_patterns(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        return _normalize_patterns(v) if v is not None else None


# ── Route response envelopes — ``{"success": true, "data": ...}`` ──


class ListInferenceTypesResponse(SuccessResponse):
    """GET /inference-types"""

    data: InferenceTypesResponse


class InferenceTypeResponse(SuccessResponse):
    """GET/POST/PUT /inference-types/{name}"""

    data: InferenceTypeItem
