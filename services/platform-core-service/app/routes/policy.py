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
from app.schemas.common import DeletedIdData, MessageMeta, error_responses
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
from app.schemas.policy_management.policy_type import (
    CreatePolicyTypeResponse,
    DeletePolicyTypeResponse,
    GetPolicyTypeResponse,
    ListPolicyTypeResponse,
    PolicyTypeCreate,
    PolicyTypeListData,
    PolicyTypeUpdate,
    UpdatePolicyTypeResponse,
)
from app.services.policy_management import category_service, sub_category_service, policy_type_service

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
    category_id: Optional[int] = Query(None, gt=0, le=2_147_483_647, description="Only sub-categories of this category."),
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


# ── Policy-type endpoints ─────────────────────────────────────────────────────


@router.get(
    "/policy-types",
    response_model=ListPolicyTypeResponse,
    responses=error_responses(403),
)
async def list_policy_types(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ListPolicyTypeResponse:
    """List every policy type. Adopter Admin only."""
    if not is_admin(request):
        raise InsufficientPermissionsError()
    items = await policy_type_service.list_policy_types(session)
    return ListPolicyTypeResponse(success=True, data=PolicyTypeListData(items=items))


@router.post(
    "/policy-types",
    response_model=CreatePolicyTypeResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(403, 409),
)
async def create_policy_type(
    payload: PolicyTypeCreate,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> CreatePolicyTypeResponse:
    """Create a policy type. Name is required and must be unique — 409 if it
    already exists. Adopter Admin only."""
    if not is_admin(request):
        raise InsufficientPermissionsError()
    user_id = request.headers.get("X-User-Id")
    item = await policy_type_service.create_policy_type(session, payload, created_by=user_id)
    return CreatePolicyTypeResponse(
        success=True,
        id=item.id,
        message=f"Policy type '{item.policy_type}' created.",
    )


@router.get(
    "/policy-types/{policy_type_id}",
    response_model=GetPolicyTypeResponse,
    responses=error_responses(403, 404),
)
async def get_policy_type(
    policy_type_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> GetPolicyTypeResponse:
    """Fetch a single policy type by ID. 404 if it does not exist.
    Adopter Admin only."""
    if not is_admin(request):
        raise InsufficientPermissionsError()
    item = await policy_type_service.get_policy_type(session, policy_type_id)
    return GetPolicyTypeResponse(success=True, data=item)


@router.put(
    "/policy-types/{policy_type_id}",
    response_model=UpdatePolicyTypeResponse,
    responses=error_responses(403, 404, 409),
)
async def update_policy_type(
    policy_type_id: int,
    payload: PolicyTypeUpdate,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> UpdatePolicyTypeResponse:
    """Update name and/or policy_fields of a policy type. 404 if it does not
    exist, 409 if the new name is already taken. Adopter Admin only."""
    if not is_admin(request):
        raise InsufficientPermissionsError()
    user_id = request.headers.get("X-User-Id")
    item = await policy_type_service.update_policy_type(session, policy_type_id, payload, updated_by=user_id)
    return UpdatePolicyTypeResponse(
        success=True,
        data=item,
        meta=MessageMeta(message=f"Policy type '{item.policy_type}' updated."),
    )


@router.delete(
    "/policy-types/{policy_type_id}",
    response_model=DeletePolicyTypeResponse,
    responses=error_responses(403, 404),
)
async def delete_policy_type(
    policy_type_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> DeletePolicyTypeResponse:
    """Delete a policy type by ID. 404 if it does not exist.
    Adopter Admin only."""
    if not is_admin(request):
        raise InsufficientPermissionsError()
    deleted_id = await policy_type_service.delete_policy_type(session, policy_type_id)
    return DeletePolicyTypeResponse(
        success=True,
        data=DeletedIdData(id=deleted_id),
        meta=MessageMeta(message=f"Policy type {deleted_id} deleted."),
    )
