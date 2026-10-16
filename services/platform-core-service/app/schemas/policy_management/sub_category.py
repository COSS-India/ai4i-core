from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import MessageMeta, SuccessResponse, SuccessResponseWithMeta
from app.schemas.policy_management.fields import (
    DESCRIPTION_MAX_LEN,
    ID_MAX,
    NAME_MAX_LEN,
    clean_description,
    clean_name,
)


class SubCategoryItem(BaseModel):
    """One row of the sub_category table."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    category_id: int
    is_active: bool


class SubCategoryListData(BaseModel):
    items: List[SubCategoryItem]


class SubCategoryCreate(BaseModel):
    """Sub-Category Name and parent Category are mandatory; Description is
    optional. Whitespace and zero-width characters are trimmed first, so a
    name with nothing visible counts as blank and 422s. category_id is strict,
    so ``true`` or ``"3"`` is rejected rather than coerced."""

    name: str = Field(..., max_length=NAME_MAX_LEN)
    description: Optional[str] = Field(None, max_length=DESCRIPTION_MAX_LEN)
    category_id: int = Field(..., gt=0, le=ID_MAX, strict=True)

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v):
        return clean_name(v, "Sub-Category")

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, v):
        return clean_description(v)


class SubCategoryStatusUpdate(BaseModel):
    """Enable or disable a sub-category without deleting it. is_active is
    strict, so ``"false"`` or ``0`` is rejected rather than coerced."""

    is_active: bool = Field(..., strict=True)


# ── Route response envelopes ──


class ListSubCategoryResponse(SuccessResponse):
    """GET /policies/sub-categories"""

    data: SubCategoryListData


class CreateSubCategoryResponse(SuccessResponseWithMeta):
    """POST /policies/sub-categories"""

    data: SubCategoryItem
    meta: MessageMeta


class UpdateSubCategoryStatusResponse(SuccessResponseWithMeta):
    """PATCH /policies/sub-categories/{sub_category_id}/status"""

    data: SubCategoryItem
    meta: MessageMeta
