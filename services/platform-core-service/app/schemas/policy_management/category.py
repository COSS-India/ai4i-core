from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import MessageMeta, SuccessResponse, SuccessResponseWithMeta
from app.schemas.policy_management.fields import (
    DESCRIPTION_MAX_LEN,
    NAME_MAX_LEN,
    clean_description,
    clean_name,
)


class CategoryItem(BaseModel):
    """One row of the category table."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    is_active: bool


class CategoryListData(BaseModel):
    items: List[CategoryItem]


class CategoryCreate(BaseModel):
    """Category Name is mandatory; Description is optional. Whitespace and
    zero-width characters are trimmed first, so a name with nothing visible
    counts as blank and 422s."""

    name: str = Field(..., max_length=NAME_MAX_LEN)
    description: Optional[str] = Field(None, max_length=DESCRIPTION_MAX_LEN)

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v):
        return clean_name(v, "Category")

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, v):
        return clean_description(v)


class CategoryStatusUpdate(BaseModel):
    """Enable or disable a category without deleting it."""

    is_active: bool


# ── Route response envelopes ──


class ListCategoryResponse(SuccessResponse):
    """GET /policies/categories"""

    data: CategoryListData


class CreateCategoryResponse(SuccessResponseWithMeta):
    """POST /policies/categories"""

    data: CategoryItem
    meta: MessageMeta


class UpdateCategoryStatusResponse(SuccessResponseWithMeta):
    """PUT /policies/categories/{category_id}"""

    data: CategoryItem
    meta: MessageMeta
