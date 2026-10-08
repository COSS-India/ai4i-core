from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import MessageMeta, SuccessResponse, SuccessResponseWithMeta


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
    """Category Name is mandatory; Description is optional. Whitespace is
    trimmed first, so a name of only spaces counts as blank and 422s."""

    name: str = Field(..., max_length=100)
    description: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Category Name is required")
        return v

    @field_validator("description")
    @classmethod
    def normalize_description(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return v.strip() or None


# ── Route response envelopes ──


class ListCategoryResponse(SuccessResponse):
    """GET /policies/categories"""

    data: CategoryListData


class CreateCategoryResponse(SuccessResponseWithMeta):
    """POST /policies/categories"""

    data: CategoryItem
    meta: MessageMeta
