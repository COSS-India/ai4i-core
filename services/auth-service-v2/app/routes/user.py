"""
User routes: profile, admin user management.
"""

from fastapi import APIRouter, Depends, Query

from app.core.exceptions import UserNotFoundError
from app.core.responses import success_response
from app.dependencies.auth import get_current_active_user
from app.dependencies.permissions import require_any_role
from app.dependencies.services import get_user_service
from app.models.user import User
from app.schemas.user import UserListResponse, UserUpdate
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["Users"])


@router.get("/me")
async def get_me(
    current_user: User = Depends(get_current_active_user),
    svc: UserService = Depends(get_user_service),
):
    profile = await svc.get_user_profile(current_user)
    return success_response(data=profile)


@router.put("/me")
async def update_me(
    body: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    svc: UserService = Depends(get_user_service),
):
    data = body.model_dump(exclude_unset=True)
    await svc.update_profile(current_user, data)
    profile = await svc.get_user_profile(current_user)
    return success_response(data=profile)


@router.get("/users")
async def list_users(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    caller: User = Depends(require_any_role("ADMIN", "MODERATOR", "TENANT ADMIN")),
    svc: UserService = Depends(get_user_service),
):
    users = await svc.list_users_for_caller(caller, offset, limit)
    items = [
        UserListResponse.model_validate(u, from_attributes=True).model_dump(by_alias=True)
        for u in users
    ]
    return success_response(data=items)


@router.get("/users/{user_id}")
async def get_user(
    user_id: int,
    caller: User = Depends(require_any_role("ADMIN", "MODERATOR", "TENANT ADMIN")),
    svc: UserService = Depends(get_user_service),
):
    user = await svc.get_user_by_id_for_caller(caller, user_id)
    if not user:
        raise UserNotFoundError()
    profile = await svc.get_user_profile(user)
    return success_response(data=profile)
