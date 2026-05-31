"""
API key CRUD routes.

Route definitions only — no business logic, no DB/Redis calls.
All operations are delegated to APIKeyService.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.responses import success_response
from app.dependencies.auth import get_current_user, get_current_user_id, get_user_context
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
    ctx = Depends(get_user_context),
    svc: APIKeyService = Depends(get_api_key_service),
):
    raw_key, api_key = await svc.create_api_key(
        user_id=ctx.user_id,
        key_name=body.key_name,
        permissions=body.permissions,
        expires_days=body.expires_days,
        tenant_id=ctx.tenant_id,
    )
    return success_response(data=CreateAPIKeyResponse(
        api_key=raw_key,
        key_name=api_key.key_name,
        permissions=api_key.permissions or [],
        expires_at=api_key.expires_at,
    ).model_dump())


@router.get("/api-keys")
async def list_api_keys(
    user_id: UUID = Depends(get_current_user_id),
    svc: APIKeyService = Depends(get_api_key_service),
):
    keys = await svc.list_by_user(user_id)
    return success_response(data={"api_keys": [_key_dict(k) for k in keys]})


@router.patch("/api-keys/{api_key}")
async def update_api_key(
    api_key: str,
    body: UpdateAPIKeyRequest,
    user_id: UUID = Depends(get_current_user_id),
    svc: APIKeyService = Depends(get_api_key_service),
):
    # Only allow updating if at least one field is provided
    update_data = body.model_dump(exclude={"api_key"}, exclude_unset=True)
    if not update_data:
        from app.core.exceptions import ValidationError
        raise ValidationError(
            message="No fields to update. Provide at least one of: key_name, permissions, expires_days, is_active.",
            code="NOTHING_TO_UPDATE",
        )

    updated_key = await svc.update_key(
        api_key_value=api_key,
        data=update_data,
        user_id=user_id,
    )
    return success_response(data={
        "api_key": updated_key.api_key,
        "key_name": updated_key.key_name,
        "user_id": str(updated_key.user_id),
        "permissions": updated_key.permissions or [],
        "expires_at": updated_key.expires_at.isoformat() if updated_key.expires_at else None,
        "is_active": updated_key.is_active,
    })


@router.delete("/api-keys/{api_key}")
async def revoke_api_key(
    api_key: str,
    user_id: UUID = Depends(get_current_user_id),
    svc: APIKeyService = Depends(get_api_key_service),
    role_svc: RoleService = Depends(get_role_service),
):
    owner_scoped_user_id = user_id
    roles = await role_svc.get_user_roles(user_id)
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
