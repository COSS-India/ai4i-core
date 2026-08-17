"""
User routes: profile, admin user management.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import RoleId
from app.core.exceptions import UserNotFoundError
from app.utils.auth_helper import check_permission_ids
from app.core.responses import to_response
from app.utils.masking import mask_pii_in_dict
from app.dependencies.auth import get_current_user
from app.dependencies.tenant_scope import enforce_target_user_same_tenant
from app.core.database import get_db
from app.dependencies.services import get_user_service
from app.models.role_name import RoleName
from app.models.user import User
from app.repositories.role_repository import RoleRepository
from app.schemas.common import error_responses
from app.schemas.user import (
    GetMeResponse,
    GetUserResponse,
    ListUsersResponse,
    UpdateMeResponse,
    UserListResponse,
    UserUpdate,
)
from app.services.user_service import UserService

router = APIRouter(
    prefix="/auth",
    tags=["Users"],
    responses=error_responses(401, 422),
)


@router.get(
    "/me",
    response_model=GetMeResponse,
)
async def get_me(
    current_user: User = Depends(get_current_user),
    svc: UserService = Depends(get_user_service),
):
    """Return the authenticated user's profile.

    Email and phone are masked.
    """
    profile = await svc.get_user_profile(current_user)
    return GetMeResponse(data=profile)


@router.put(
    "/me",
    response_model=UpdateMeResponse,
)
async def update_me(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    svc: UserService = Depends(get_user_service),
):
    """Update the authenticated user's profile fields.

    Masked email/phone values echoed back from a previous response are
    dropped so they do not overwrite stored plaintext.
    """
    data = body.model_dump(exclude_unset=True)
    await svc.update_profile(current_user, data)
    # Reload the user from the database after update to avoid accessing
    # potentially expired attributes on the in-memory instance, which can
    # trigger async IO in an unsafe context.
    refreshed_user = await svc.get_user_by_id(current_user.id)
    # Fallback to the original user object if for some reason the reload fails.
    profile = await svc.get_user_profile(refreshed_user or current_user)
    return UpdateMeResponse(data=profile)


@router.get(
    "/users",
    response_model=ListUsersResponse,
    responses=error_responses(403),
)
async def list_users(
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    caller: User = Depends(get_current_user),
    svc: UserService = Depends(get_user_service),
    db: AsyncSession = Depends(get_db),
):
    """List users visible to the caller.

    Requires ADMIN, MODERATOR, or TENANT_ADMIN (via gateway permission IDs).
    Tenant admins only see users in their own tenant. Email and phone are
    masked.
    """
    check_permission_ids(request, RoleId.ADMIN, RoleId.MODERATOR, RoleId.TENANT_ADMIN)
    user_roles = await RoleRepository(db).get_user_roles(caller.id)
    request.state.user_roles = user_roles
    users = await svc.list_users_for_caller(caller, offset, limit, role_set=set(user_roles))
    items = [mask_pii_in_dict(to_response(u, UserListResponse)) for u in users]
    return ListUsersResponse(data=items)


@router.get(
    "/users/{user_id}",
    response_model=GetUserResponse,
    responses=error_responses(403, 404),
)
async def get_user(
    request: Request,
    user_id: UUID,
    caller: User = Depends(get_current_user),
    svc: UserService = Depends(get_user_service),
    db: AsyncSession = Depends(get_db),
):
    """Return one user's full profile.

    Requires ADMIN or TENANT_ADMIN. Tenant admins may only fetch users in
    their own tenant. Email and phone are masked. 404 if the user does not
    exist.
    """
    check_permission_ids(request, RoleId.ADMIN, RoleId.TENANT_ADMIN)
    await enforce_target_user_same_tenant(
        request,
        caller,
        user_id,
        db,
        bypass_roles=(RoleName.ADMIN,),
    )
    user_roles = await RoleRepository(db).get_user_roles(caller.id)
    user = await svc.get_user_by_id_for_caller(caller, user_id, role_set=set(user_roles))
    if not user:
        raise UserNotFoundError()
    profile = await svc.get_user_profile(user)
    return GetUserResponse(data=profile)
