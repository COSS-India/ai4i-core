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
    category_id: int = Field(..., gt=0, le=2_147_483_647)

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v):
        # Runs before max_length so padding does not count toward the limit;
        # non-strings fall through to the str type check.
        if not isinstance(v, str):
            return v
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


# ── Route response envelopes ──


class ListSubCategoryResponse(SuccessResponse):
    """GET /policies/sub-categories"""

    data: SubCategoryListData


class CreateSubCategoryResponse(SuccessResponseWithMeta):
    """POST /policies/sub-categories"""

    data: SubCategoryItem
    meta: MessageMeta
