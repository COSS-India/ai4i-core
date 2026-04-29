"""
API key CRUD routes.

Route definitions only — no business logic, no DB/Redis calls.
All operations are delegated to APIKeyService.
"""

from fastapi import APIRouter, Depends, Query

from app.core.responses import success_response
from app.dependencies.auth import get_current_active_user
from app.dependencies.permissions import require_any_role
from app.dependencies.services import get_api_key_service, get_role_service
from app.models.role_name import RoleName
from app.models.user import User
from app.schemas.api_key import (
    CreateAPIKeyRequest,
    CreateAPIKeyResponse,
    UpdateAPIKeyRequest,
)
from app.services.api_key_service import APIKeyService
from app.services.role_service import RoleService

router = APIRouter(prefix="/auth", tags=["API Keys"])


def _key_dict(k) -> dict:
    return {
        "api_key": k.api_key,
        "key_name": k.key_name,
        "user_id": str(k.user_id),
        "permissions": k.permissions or [],
        "expires_at": k.expires_at.isoformat() if k.expires_at else None,
        "is_active": k.is_active,
        "created_at": k.created_at.isoformat() if k.created_at else None,
        "updated_at": k.updated_at.isoformat() if k.updated_at else None,
    }


@router.post("/api-keys")
async def create_api_key(
    body: CreateAPIKeyRequest,
    current_user: User = Depends(get_current_active_user),
    svc: APIKeyService = Depends(get_api_key_service),
):
    raw_key, api_key = await svc.create_api_key(
        user_id=current_user.id,
        key_name=body.key_name,
        permissions=body.permissions,
        expires_days=body.expires_days,
        tenant_id=str(current_user.tenant_id) if current_user.tenant_id else None,
    )
    return success_response(data=CreateAPIKeyResponse(
        api_key=raw_key,
        key_name=api_key.key_name,
        permissions=api_key.permissions or [],
        expires_at=api_key.expires_at,
    ).model_dump())


@router.get("/api-keys")
async def list_api_keys(
    current_user: User = Depends(get_current_active_user),
    svc: APIKeyService = Depends(get_api_key_service),
):
    keys = await svc.list_by_user(current_user.id)
    return success_response(data={"api_keys": [_key_dict(k) for k in keys]})


@router.patch("/api-keys")
async def update_api_key(
    body: UpdateAPIKeyRequest,
    current_user: User = Depends(get_current_active_user),
    svc: APIKeyService = Depends(get_api_key_service),
):
    update_data = body.model_dump(exclude={"api_key"}, exclude_unset=True)
    api_key = await svc.update_key(
        api_key_value=body.api_key,
        data=update_data,
        user_id=current_user.id,
    )
    return success_response(data={
        "key_name": api_key.key_name,
        "user_id": str(api_key.user_id),
        "permissions": api_key.permissions or [],
        "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
        "is_active": api_key.is_active,
    })


@router.delete("/api-keys/{api_key}")
async def revoke_api_key(
    api_key: str,
    current_user: User = Depends(get_current_active_user),
    svc: APIKeyService = Depends(get_api_key_service),
    role_svc: RoleService = Depends(get_role_service),
):
    owner_scoped_user_id = current_user.id
    roles = await role_svc.get_user_roles(current_user.id)
    if RoleName.ADMIN.value in roles:
        owner_scoped_user_id = None

    await svc.revoke_api_key(api_key, user_id=owner_scoped_user_id)
    return success_response(data={"message": "API key revoked."})


@router.get("/api-keys/all")
async def list_all_api_keys(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    _admin: User = Depends(require_any_role(RoleName.ADMIN, RoleName.MODERATOR)),
    svc: APIKeyService = Depends(get_api_key_service),
):
    results = await svc.list_all_with_users(offset, limit)
    items = [
        {
            **_key_dict(api_key),
            "user_email": user.email,
            "username": user.username,
        }
        for api_key, user in results
    ]
    return success_response(data=items)
