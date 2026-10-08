from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import MessageMeta, SuccessResponse, SuccessResponseWithMeta


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
    optional. Whitespace is trimmed first, so a name of only spaces counts as
    blank and 422s."""

    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    category_id: int = Field(..., gt=0)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Sub-Category Name is required")
        return v

    @field_validator("description")
    @classmethod
    def normalize_description(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return v.strip() or None


class SubCategoryStatusUpdate(BaseModel):
    """Enable or disable a sub-category without deleting it."""

    is_active: bool


# ── Route response envelopes ──


class ListSubCategoryResponse(SuccessResponse):
    """GET /policies/sub-categories"""

    data: SubCategoryListData


class CreateSubCategoryResponse(SuccessResponseWithMeta):
    """POST /policies/sub-categories"""

    data: SubCategoryItem
    meta: MessageMeta


class UpdateSubCategoryStatusResponse(SuccessResponseWithMeta):
    """PUT /policies/sub-categories/{sub_category_id}"""

    data: SubCategoryItem
    meta: MessageMeta
