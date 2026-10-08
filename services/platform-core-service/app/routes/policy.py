"""Policy-management endpoints — Adopter-facing, ADMIN only.

Categories are the top level of the policy hierarchy; a category is created
before any sub-categories or policies exist under it. Each sub-category
belongs to exactly one category.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import InsufficientPermissionsError
from app.core.permissions import is_admin
from app.schemas.common import MessageMeta, error_responses
from app.schemas.policy_management.category import (
    CategoryCreate,
    CategoryListData,
    CreateCategoryResponse,
    ListCategoryResponse,
)
from app.schemas.policy_management.sub_category import (
    CreateSubCategoryResponse,
    ListSubCategoryResponse,
    SubCategoryCreate,
    SubCategoryListData,
)
from app.services.policy_management import category_service, sub_category_service

router = APIRouter(
    prefix="/policies",
    tags=["Policies"],
)


@router.get("/categories", response_model=ListCategoryResponse, responses=error_responses(403))
async def list_categories(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ListCategoryResponse:
    """List every policy category. Adopter Admin only."""
    if not is_admin(request):
        raise InsufficientPermissionsError()
    items = await category_service.list_categories(session)
    return ListCategoryResponse(success=True, data=CategoryListData(items=items))


@router.post(
    "/categories",
    response_model=CreateCategoryResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(403, 409),
)
async def create_category(
    payload: CategoryCreate,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> CreateCategoryResponse:
    """Create a category. Name is required and must be unique
    (case-insensitive) — 409 if it already exists. Adopter Admin only."""
    if not is_admin(request):
        raise InsufficientPermissionsError()
    item = await category_service.create_category(session, payload)
    return CreateCategoryResponse(
        success=True, data=item, meta=MessageMeta(message=f"Category '{item.name}' created.")
    )


@router.get(
    "/sub-categories", response_model=ListSubCategoryResponse, responses=error_responses(403, 404)
)
async def list_sub_categories(
    request: Request,
    category_id: Optional[int] = Query(None, gt=0, description="Only sub-categories of this category."),
    session: AsyncSession = Depends(get_db),
) -> ListSubCategoryResponse:
    """List sub-categories, optionally only those under one category (404 if
    that category does not exist). Adopter Admin only."""
    if not is_admin(request):
        raise InsufficientPermissionsError()
    items = await sub_category_service.list_sub_categories(session, category_id)
    return ListSubCategoryResponse(success=True, data=SubCategoryListData(items=items))


@router.post(
    "/sub-categories",
    response_model=CreateSubCategoryResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(403, 404, 409),
)
async def create_sub_category(
    payload: SubCategoryCreate,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> CreateSubCategoryResponse:
    """Create a sub-category under an existing category. Name and parent
    category are required; 404 if the category does not exist, 409 if the
    name is already taken (case-insensitive). Adopter Admin only."""
    if not is_admin(request):
        raise InsufficientPermissionsError()
    item = await sub_category_service.create_sub_category(session, payload)
    return CreateSubCategoryResponse(
        success=True, data=item, meta=MessageMeta(message=f"Sub-category '{item.name}' created.")
    )
