"""
User routes: profile, admin user management.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UserNotFoundError
from app.core.responses import platform_success_response
from app.dependencies.auth import get_current_active_user
from app.dependencies.permissions import require_any_role
from app.dependencies.tenant_scope import enforce_target_user_same_tenant
from app.core.database import get_db
from app.dependencies.services import get_user_service
from app.models.role_name import RoleName
from app.models.user import User
from app.schemas.user import UserListResponse, UserUpdate
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["Users"])


@router.get("/me")
async def get_me(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    svc: UserService = Depends(get_user_service),
):
    profile = await svc.get_user_profile(current_user)
    request_id = getattr(request.state, "platform_request_id", None)
    return platform_success_response(data=profile, request_id=request_id)


@router.put("/me")
async def update_me(
    request: Request,
    body: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    svc: UserService = Depends(get_user_service),
):
    data = body.model_dump(exclude_unset=True)
    await svc.update_profile(current_user, data)
    # Reload the user from the database after update to avoid accessing
    # potentially expired attributes on the in-memory instance, which can
    # trigger async IO in an unsafe context.
    refreshed_user = await svc.get_user_by_id(current_user.id)
    # Fallback to the original user object if for some reason the reload fails.
    profile = await svc.get_user_profile(refreshed_user or current_user)
    request_id = getattr(request.state, "platform_request_id", None)
    return platform_success_response(data=profile, request_id=request_id)


@router.get("/users")
async def list_users(
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    caller: User = Depends(require_any_role(RoleName.ADMIN, RoleName.MODERATOR, RoleName.TENANT_ADMIN)),
    svc: UserService = Depends(get_user_service),
):
    role_set = set(getattr(request.state, "user_roles", []) or [])
    users = await svc.list_users_for_caller(caller, offset, limit, role_set=role_set)
    items = [
        UserListResponse.model_validate(u, from_attributes=True).model_dump(mode="json")
        for u in users
    ]
    request_id = getattr(request.state, "platform_request_id", None)
    return platform_success_response(data=items, request_id=request_id)


@router.get("/users/{user_id}")
async def get_user(
    request: Request,
    user_id: UUID,
    caller: User = Depends(require_any_role(RoleName.ADMIN, RoleName.MODERATOR, RoleName.TENANT_ADMIN)),
    svc: UserService = Depends(get_user_service),
    db: AsyncSession = Depends(get_db),
):
    # Enforce tenant isolation for TENANT ADMIN using the shared helper.
    await enforce_target_user_same_tenant(
        request,
        caller,
        user_id,
        db,
        bypass_roles=(RoleName.ADMIN, RoleName.MODERATOR),
    )
    role_set = set(getattr(request.state, "user_roles", []) or [])
    user = await svc.get_user_by_id_for_caller(caller, user_id, role_set=role_set)
    if not user:
        raise UserNotFoundError()
    profile = await svc.get_user_profile(user)
    request_id = getattr(request.state, "platform_request_id", None)
    return platform_success_response(data=profile, request_id=request_id)
