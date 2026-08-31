"""
API key CRUD routes.

Route definitions only — no business logic, no DB/Redis calls.
All operations are delegated to APIKeyService.

Ownership/scope: a key belongs to an Application, which belongs to a Tenant.
TENANT_ADMIN is scoped to their own tenant's applications; ADMIN is unscoped.
"""

import logging
from decimal import Decimal
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_platform_core_db
from app.core.exceptions import EntityNotFoundError, ValidationError

from app.dependencies.permissions import require_any_role
from app.dependencies.services import get_api_key_service
from app.core.constants import RoleName
from app.models.user import User
from app.schemas.api_key import (
    APIKeyAdminItem,
    APIKeyItem,
    ApplicationAPIKeysGroup,
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
from app.services import budget_usage
from app.services.api_key_service import APIKeyService
from app.utils.masking import mask_api_key

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/auth",
    tags=["API Keys"],
    responses=error_responses(401),
)

_KeyId = Annotated[int, Path(ge=1, description="Numeric ID of the API key.")]


def _is_admin(request: Request) -> bool:
    """require_any_role already fetched the caller's roles for this request;
    reuse them instead of a second DB round trip."""
    return RoleName.ADMIN.value in getattr(request.state, "user_roles", [])


def _resolve_caller_tenant_scope(request: Request, current_user: User) -> Optional[int]:
    """None means platform ADMIN — unscoped. Otherwise the caller's own
    tenant_id, which must actually be set: User.tenant_id is nullable
    (ON DELETE SET NULL on the tenants FK), so a non-admin caller with a
    null tenant_id must be rejected outright here rather than falling
    through to caller_tenant_id=None — every downstream lookup
    (get_by_id_for_scope, list_grouped, create_api_key) reads None as
    "platform admin, unscoped", which would let such a caller list/create
    keys across every tenant. Same fail-closed convention as
    TenantService.enforce_scope.
    """
    if _is_admin(request):
        return None
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "TENANT_FORBIDDEN",
                "message": "Cannot access a tenant you do not belong to.",
            },
        )
    return current_user.tenant_id


def _key_item(k, *, permission_names: list[str]) -> APIKeyItem:
    return APIKeyItem(
        id=k.id,
        key_name=k.key_name,
        api_key=mask_api_key(k.api_key),
        allocated_percentage=k.allocated_percentage,
        allocated_budget=k.allocated_budget,
        permissions=permission_names,
        expires_at=k.expires_at,
        is_active=k.is_active,
        created_by=str(k.created_by) if k.created_by else None,
        created_at=k.created_at,
        updated_at=k.updated_at,
    )


def _key_items_from_map(keys, id_to_name: dict[int, str]) -> list[APIKeyItem]:
    """Shape keys into response items from an already-resolved id->name map —
    the caller resolves the map once, so multi-group callers (list_api_keys)
    don't issue one get_permission_names_by_ids query per group."""

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


async def _key_items_for_response(svc: APIKeyService, keys) -> list[APIKeyItem]:
    """Single-group convenience wrapper — resolves permission names for just
    this one key list. Not used where multiple groups share one response
    (see list_api_keys, which hoists the lookup across all of them instead)."""
    id_to_name = await svc.permission_name_map_for_keys(keys)
    return _key_items_from_map(keys, id_to_name)


@router.post(
    "/api-keys",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateAPIKeyResponse,
    summary="Create API key",
    responses=error_responses(403, 404),
)
async def create_api_key(
    body: CreateAPIKeyRequest,
    request: Request,
    current_user: User = Depends(require_any_role(RoleName.ADMIN, RoleName.TENANT_ADMIN)),
    svc: APIKeyService = Depends(get_api_key_service),
    platform_core_db: Optional[AsyncSession] = Depends(get_platform_core_db),
):
    """Create an API key under an Application.

    The raw 32-character hex key is returned **once** and cannot be retrieved
    again. `permissions` are stable names (e.g. `nmt.inference`), not numeric
    IDs. TENANT_ADMIN may only target an application in their own tenant
    (a mismatched or unknown `application_id` returns 404
    APPLICATION_NOT_FOUND, uniformly); ADMIN may target any tenant's
    application. The Application's tenant must have an active tier
    (`tenants.tier_id`), or this returns 422 NO_ACTIVE_TIER.
    """
    caller_tenant_id = _resolve_caller_tenant_scope(request, current_user)
    raw_key, api_key = await svc.create_api_key(
        actor_user_id=current_user.id,
        key_name=body.key_name,
        permissions=body.permissions,
        application_id=body.application_id,
        expires_days=body.expires_days,
        allocated_percentage=body.allocated_percentage,
        budget=body.budget,
        caller_tenant_id=caller_tenant_id,
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
            application_id=api_key.application_id,
            allocated_percentage=api_key.allocated_percentage,
            allocated_budget=api_key.allocated_budget,
        )
    )


@router.get(
    "/api-keys",
    response_model=ListAPIKeysResponse,
    summary="List API keys",
    responses=error_responses(403, 404),
)
async def list_api_keys(
    request: Request,
    application_id: Optional[int] = Query(
        None, description="Restrict to one Application's keys."
    ),
    offset: int = Query(
        0, ge=0, description="Applications to skip. Ignored when application_id is set."
    ),
    limit: int = Query(
        100, ge=1, le=500,
        description="Maximum Applications to return (each with all its keys). Ignored when application_id is set.",
    ),
    current_user: User = Depends(require_any_role(RoleName.ADMIN, RoleName.TENANT_ADMIN)),
    svc: APIKeyService = Depends(get_api_key_service),
):
    """List API keys, grouped by Application.

    TENANT_ADMIN sees every key under their own tenant's Applications; ADMIN
    sees every key across every tenant, paginated by Application via
    `offset`/`limit` (each page still returns every key under the
    Applications it includes). Either may narrow to one Application via
    `application_id` — for TENANT_ADMIN it must belong to their tenant, or
    this returns 404 APPLICATION_NOT_FOUND. Returned `api_key` values are
    masked.
    """
    caller_tenant_id = _resolve_caller_tenant_scope(request, current_user)
    groups = await svc.list_grouped(
        caller_tenant_id=caller_tenant_id,
        application_id=application_id,
        offset=offset,
        limit=limit,
    )
    # Resolve permission names once across every group's keys combined,
    # rather than once per group (get_permission_names_by_ids is otherwise
    # one query per Application on top of a response already carrying every
    # key it groups).
    all_keys = [key for _application, keys in groups for key in keys]
    id_to_name = await svc.permission_name_map_for_keys(all_keys)
    data = [
        ApplicationAPIKeysGroup(
            application_id=application.id,
            api_keys=_key_items_from_map(keys, id_to_name),
        )
        for application, keys in groups
    ]
    return ListAPIKeysResponse(data=data)


@router.patch(
    "/api-keys/{key_id}",
    response_model=UpdateAPIKeyResponse,
    summary="Update API key",
    responses=error_responses(404),
)
async def update_api_key(
    key_id: _KeyId,
    body: UpdateAPIKeyRequest,
    request: Request,
    current_user: User = Depends(require_any_role(RoleName.ADMIN, RoleName.TENANT_ADMIN)),
    svc: APIKeyService = Depends(get_api_key_service),
):
    """Update an API key.

    Provide at least one of `key_name`, `permissions`, or `expires_days`.
    Scoped to the caller's tenant (via the key's Application) unless ADMIN;
    a key outside that scope returns 404, same as a nonexistent one.
    Returned `api_key` is masked.
    """
    update_data = body.model_dump(exclude={"api_key"}, exclude_unset=True)
    if not update_data:
        raise ValidationError(
            message="No fields to update. Provide at least one of: key_name, permissions, expires_days.",
            code="NOTHING_TO_UPDATE",
        )

    caller_tenant_id = _resolve_caller_tenant_scope(request, current_user)
    db_key = await svc.get_by_id_for_scope(key_id, caller_tenant_id)
    if not db_key:
        raise EntityNotFoundError("API key")

    updated_key = await svc.update_key_by_obj(db_key, update_data, current_user.id)
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
    request: Request,
    current_user: User = Depends(require_any_role(RoleName.ADMIN, RoleName.TENANT_ADMIN)),
    svc: APIKeyService = Depends(get_api_key_service),
):
    """Revoke an API key (`is_active=false`).

    Scoped to the caller's tenant (via the key's Application) unless ADMIN;
    a key outside that scope returns 404, same as a nonexistent one.
    """
    caller_tenant_id = _resolve_caller_tenant_scope(request, current_user)
    db_key = await svc.get_by_id_for_scope(key_id, caller_tenant_id)
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
    platform_core_db: Optional[AsyncSession] = Depends(get_platform_core_db),
):
    """Paginated, flat list of every API key across every tenant.

    Requires ADMIN or MODERATOR. Keys are masked; there is no owner PII to
    mask or return any more (keys are owned by Applications, not Users).
    `budget_used`/`budget_pending` are read from platform-core's per-key
    usage ledger and are `None` if that DB isn't reachable or has no usage
    row yet for a key with no `allocated_budget` set.
    """
    results = await svc.list_all_with_applications(offset, limit)
    keys = [api_key for api_key, _application in results]
    items = await _key_items_for_response(svc, keys)
    usage = await budget_usage.fetch_budget_usage([k.id for k in keys], platform_core_db)

    data = []
    for item, (api_key, _application) in zip(items, results):
        used, _snap = usage.get(api_key.id, (None, None))
        if api_key.allocated_budget is None:
            budget_used, budget_pending = used, None
        else:
            budget_used = used if used is not None else Decimal("0")
            budget_pending = api_key.allocated_budget - budget_used
        data.append(
            APIKeyAdminItem(
                **item.model_dump(),
                application_id=api_key.application_id,
                budget_used=budget_used,
                budget_pending=budget_pending,
            )
        )
    return ListAllAPIKeysResponse(data=data)
