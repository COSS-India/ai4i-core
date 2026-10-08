"""Policy-management endpoints — Adopter-facing, ADMIN only.

Categories are the top level of the policy hierarchy; a category is created
before any sub-categories or policies exist under it.
"""

from fastapi import APIRouter, Depends, Request, status
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
from app.services.policy_management import category_service

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
