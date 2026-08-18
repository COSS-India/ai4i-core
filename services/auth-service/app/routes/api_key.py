"""
API key CRUD routes.

Route definitions only — no business logic, no DB/Redis calls.
All operations are delegated to APIKeyService.
"""

import logging
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_platform_core_db

from app.dependencies.auth import get_current_user, get_current_user_id, get_user_context
from app.dependencies.permissions import require_any_role
from app.dependencies.services import get_api_key_service, get_role_service
from app.models.role_name import RoleName
from app.models.user import User
from app.schemas.api_key import (
    APIKeyAdminItem,
    APIKeyItem,
    APIKeyListData,
    CreateAPIKeyData,
    CreateAPIKeyRequest,
    CreateAPIKeyResponse,
    ListAllAPIKeysResponse,
    ListAPIKeysResponse,
    RevokeAPIKeyResponse,
    UpdateAPIKeyRequest,
    UpdateAPIKeyResponse,
)
from app.schemas.common import MessageData, error_responses
from app.services.api_key_service import APIKeyService
from app.services.role_service import RoleService
from app.utils.masking import mask_api_key, mask_email

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/auth",
    tags=["API Keys"],
    responses=error_responses(401),
)

_KeyId = Annotated[int, Path(ge=1, description="Numeric ID of the API key.")]


def _key_item(k, *, permission_names: list[str]) -> APIKeyItem:
    return APIKeyItem(
        id=k.id,
        key_name=k.key_name,
        api_key=mask_api_key(k.api_key),
        user_id=str(k.user_id),
        permissions=permission_names,
        expires_at=k.expires_at,
        is_active=k.is_active,
        created_at=k.created_at,
        updated_at=k.updated_at,
    )


async def _key_items_for_response(svc: APIKeyService, keys) -> list[APIKeyItem]:
    """Batch-resolve stored permission IDs to names for list responses."""
    id_to_name = await svc.permission_name_map_for_keys(keys)

    def names_for(key) -> list[str]:
        names = []
        for pid in (key.permissions or []):
            name = id_to_name.get(pid)
            if name is None:
                logger.warning(
                    "api_key id=%s references unknown permission id=%s", key.id, pid
                )
                continue
            names.append(name)
        return names

    return [_key_item(k, permission_names=names_for(k)) for k in keys]


@router.post(
    "/api-keys",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateAPIKeyResponse,
    summary="Create API key",
)
async def create_api_key(
    body: CreateAPIKeyRequest,
    ctx = Depends(get_user_context),
    svc: APIKeyService = Depends(get_api_key_service),
    platform_core_db: Optional[AsyncSession] = Depends(get_platform_core_db),
):
    """Create an API key for the authenticated user.

    The raw 32-character hex key is returned **once** and cannot be retrieved
    again. The caller must belong to a tenant with an active PPU tier
    assignment. `permissions` are stable names (e.g. `nmt.inference`), not
    numeric IDs.
    """
    raw_key, api_key = await svc.create_api_key(
        user_id=ctx.user_id,
        key_name=body.key_name,
        permissions=body.permissions,
        expires_days=body.expires_days,
        tenant_id=ctx.tenant_id,
        platform_core_db=platform_core_db,
    )
    permission_names = await svc.permission_ids_to_names(
        api_key.permissions or [], api_key_id=api_key.id
    )
    return CreateAPIKeyResponse(
        data=CreateAPIKeyData(
            id=api_key.id,
            api_key=raw_key,
            key_name=api_key.key_name,
            permissions=permission_names,
            expires_at=api_key.expires_at,
        )
    )


@router.get(
    "/api-keys",
    response_model=ListAPIKeysResponse,
    summary="List own API keys",
    responses=error_responses(403),
)
async def list_api_keys(
    user_id: UUID = Depends(get_current_user_id),
    _admin: User = Depends(require_any_role(RoleName.ADMIN, RoleName.TENANT_ADMIN)),
    svc: APIKeyService = Depends(get_api_key_service),
):
    """List API keys owned by the authenticated user.

    Returned `api_key` values are masked. Requires ADMIN or TENANT_ADMIN.
    """
    keys = await svc.list_by_user(user_id)
    items = await _key_items_for_response(svc, keys)
    return ListAPIKeysResponse(data=APIKeyListData(api_keys=items))


@router.patch(
    "/api-keys/{key_id}",
    response_model=UpdateAPIKeyResponse,
    summary="Update API key",
    responses=error_responses(404),
)
async def update_api_key(
    key_id: _KeyId,
    body: UpdateAPIKeyRequest,
    user_id: UUID = Depends(get_current_user_id),
    svc: APIKeyService = Depends(get_api_key_service),
):
    """Update an API key owned by the authenticated user.

    Provide at least one of `key_name`, `permissions`, or `expires_days`.
    Ownership-scoped: a key that does not exist or belongs to another user
    both return 404. Returned `api_key` is masked.
    """
    from app.core.exceptions import EntityNotFoundError, ValidationError

    update_data = body.model_dump(exclude={"api_key"}, exclude_unset=True)
    if not update_data:
        raise ValidationError(
            message="No fields to update. Provide at least one of: key_name, permissions, expires_days.",
            code="NOTHING_TO_UPDATE",
        )

    # Ownership-scoped: returns None whether the key doesn't exist or belongs to
    # another user, so the caller cannot enumerate valid key IDs.
    db_key = await svc.get_by_id_for_owner(key_id, user_id)
    if not db_key:
        raise EntityNotFoundError("API key")

    updated_key = await svc.update_key_by_obj(db_key, update_data, user_id)
    permission_names = await svc.permission_ids_to_names(
        updated_key.permissions or [], api_key_id=updated_key.id
    )
    return UpdateAPIKeyResponse(
        data=_key_item(updated_key, permission_names=permission_names)
    )


@router.delete(
    "/api-keys/{key_id}",
    response_model=RevokeAPIKeyResponse,
    summary="Revoke API key",
    responses=error_responses(404),
)
async def revoke_api_key(
    key_id: _KeyId,
    user_id: UUID = Depends(get_current_user_id),
    svc: APIKeyService = Depends(get_api_key_service),
    role_svc: RoleService = Depends(get_role_service),
):
    """Revoke an API key (`is_active=false`).

    Owners may revoke their own keys; admins may revoke any key. Non-admin
    callers receive 404 whether the key does not exist or belongs to someone
    else.
    """
    from app.core.exceptions import EntityNotFoundError

    roles = await role_svc.get_user_roles(user_id)
    is_admin = RoleName.ADMIN.value in roles

    # Admins can revoke any key (unscoped); regular users get a uniform 404
    # whether the key doesn't exist or belongs to someone else.
    db_key = (
        await svc.get_by_id(key_id)
        if is_admin
        else await svc.get_by_id_for_owner(key_id, user_id)
    )
    if not db_key:
        raise EntityNotFoundError("API key")

    await svc.revoke_by_obj(db_key)
    return RevokeAPIKeyResponse(data=MessageData(message="API key revoked."))


@router.get(
    "/api-keys/all",
    response_model=ListAllAPIKeysResponse,
    summary="List all API keys",
    responses=error_responses(403),
)
async def list_all_api_keys(
    offset: int = Query(0, ge=0, description="Number of records to skip."),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of records to return."),
    _admin: User = Depends(require_any_role(RoleName.ADMIN, RoleName.MODERATOR)),
    svc: APIKeyService = Depends(get_api_key_service),
):
    """Paginated list of every API key, including masked owner email and username.

    Requires ADMIN or MODERATOR. Keys and emails are masked; plaintext PII is
    never returned.
    """
    results = await svc.list_all_with_users(offset, limit)
    keys = [api_key for api_key, _user in results]
    items = await _key_items_for_response(svc, keys)
    return ListAllAPIKeysResponse(
        data=[
            APIKeyAdminItem(
                **item.model_dump(),
                # Email is decrypted transparently by the column type; mask it so this
                # admin/moderator endpoint never returns plaintext PII.
                user_email=mask_email(user.email),
                username=user.username,
            )
            for item, (_api_key, user) in zip(items, results)
        ]
    )
