from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


class SubCategoryUpdate(BaseModel):
    """Partial update: only the fields sent change, and at least one is
    required. Name is cleaned like on create and can't be null or blank;
    a null or blank description clears it. A new category_id moves the
    sub-category under that category; it is strict and can't be null."""

    name: Optional[str] = Field(None, max_length=NAME_MAX_LEN)
    description: Optional[str] = Field(None, max_length=DESCRIPTION_MAX_LEN)
    category_id: Optional[int] = Field(None, gt=0, le=ID_MAX, strict=True)

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v):
        return clean_name(v, "Sub-Category")

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, v):
        return clean_description(v)

    @model_validator(mode="after")
    def check_fields(self):
        if not self.model_fields_set:
            raise ValueError("At least one of name, description or category_id is required")
        if "category_id" in self.model_fields_set and self.category_id is None:
            raise ValueError("category_id cannot be null")
        return self


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


class UpdateSubCategoryResponse(SuccessResponseWithMeta):
    """PATCH /policies/sub-categories/{sub_category_id}"""

    data: SubCategoryItem
    meta: MessageMeta
