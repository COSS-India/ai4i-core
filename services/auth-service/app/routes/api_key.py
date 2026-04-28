"""
API key CRUD routes.
"""

from fastapi import APIRouter, Depends, Query

from app.core.exceptions import EntityNotFoundError
from app.core.responses import success_response
from app.dependencies.auth import get_current_active_user
from app.dependencies.permissions import require_any_role
from app.dependencies.services import get_api_key_service, get_role_service
from app.models.user import User
from app.schemas.api_key import (
    APIKeyCreateRequest,
    APIKeyResponse,
    APIKeyUpdateRequest,
    APIKeyValidationRequest,
    APIKeyValidationResponse,
)
from app.services.api_key_service import APIKeyService
from app.services.role_service import RoleService

router = APIRouter(prefix="/auth", tags=["API Keys"])


@router.post("/api-keys")
async def create_api_key(
    body: APIKeyCreateRequest,
    current_user: User = Depends(get_current_active_user),
    svc: APIKeyService = Depends(get_api_key_service),
):
    tenant_id = str(current_user.tenant_id) if current_user.tenant_id else None
    jwt_token, api_key = await svc.create_api_key(
        user_id=current_user.id,
        key_name=body.key_name,
        permissions=body.permissions,
        tenant_id=tenant_id,
        expires_days=body.expires_days,
    )
    stored = api_key.permissions or {}
    permission_ids = stored.get("permission", []) if isinstance(stored, dict) else stored
    return success_response(data={
        "key_id": api_key.id,
        "key_name": api_key.key_name,
        "api_key": jwt_token,
        "permissions": permission_ids,
        "is_active": api_key.is_active,
        "created_at": api_key.created_at.isoformat() if api_key.created_at else None,
        "message": "API key created. Store it securely — it will not be shown again.",
    })


@router.get("/api-keys")
async def list_api_keys(
    current_user: User = Depends(get_current_active_user),
    svc: APIKeyService = Depends(get_api_key_service),
):
    keys = await svc.list_by_user(current_user.id)
    items = [APIKeyResponse.model_validate(k, from_attributes=True).model_dump() for k in keys]
    return success_response(data={"api_keys": items})


@router.patch("/api-keys/{key_id}")
async def update_api_key(
    key_id: int,
    body: APIKeyUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    svc: APIKeyService = Depends(get_api_key_service),
):
    data = body.model_dump(exclude_unset=True)
    api_key = await svc.update_key(key_id, data, user_id=current_user.id)
    return success_response(data=APIKeyResponse.model_validate(api_key, from_attributes=True).model_dump())


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    current_user: User = Depends(get_current_active_user),
    svc: APIKeyService = Depends(get_api_key_service),
    role_svc: RoleService = Depends(get_role_service),
):
    owner_scoped_user_id = current_user.id
    roles = await role_svc.get_user_roles(current_user.id)
    if "ADMIN" in roles:
        owner_scoped_user_id = None

    await svc.revoke_api_key(key_id, user_id=owner_scoped_user_id)
    return success_response(data={"message": "API key revoked."})


@router.get("/api-keys/all")
async def list_all_api_keys(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    _admin: User = Depends(require_any_role("ADMIN", "MODERATOR")),
    svc: APIKeyService = Depends(get_api_key_service),
):
    results = await svc.list_all_with_users(offset, limit)
    items = []
    for api_key, user in results:
        item = APIKeyResponse.model_validate(api_key, from_attributes=True).model_dump()
        item["user_id"] = str(user.id)
        item["user_email"] = user.email
        item["username"] = user.username
        items.append(item)
    return success_response(data=items)


@router.post("/validate-api-key")
async def validate_api_key(
    body: APIKeyValidationRequest,
    svc: APIKeyService = Depends(get_api_key_service),
):
    result = await svc.validate_api_key_jwt(
        jwt_token=body.api_key,
        required_service=body.service,
        required_action=body.action,
        expected_user_id=body.user_id,
    )
    return APIKeyValidationResponse(**result)
