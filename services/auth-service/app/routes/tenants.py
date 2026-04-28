"""Tenant + tenant-user CRUD routes."""

import logging
import re
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import EntityNotFoundError
from app.core.responses import success_response
from app.dependencies.auth import get_current_active_user
from app.core.roles import Roles
from app.dependencies.services import get_auth_service
from app.models.tenant import Tenant, TenantStatus
from app.models.role_name import RoleName
from app.models.user import CreationType, User
from app.repositories.role_repository import RoleRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.schemas.tenant import (
    TenantCreate,
    TenantResponse,
    TenantStatusUpdate,
    TenantUpdate,
    TenantUserCreate,
    TenantUserCreateResponse,
    TenantUserStatusUpdate,
    TenantUserUpdate,
)
from app.schemas.user import UserListResponse
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)


def _derive_username_from_email(email: str) -> str:
    """Build a default username from the email's local part.

    Used when auto-provisioning a tenant admin from the contact email — the
    admin doesn't pick a username, the system derives one. Replaces non
    [a-zA-Z0-9_] chars with underscores; falls back to "user" if empty.
    """
    local = email.split("@", 1)[0]
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", local).strip("_") or "user"
    if len(sanitized) < 3:
        sanitized = (sanitized + "_user")[:100]
    return sanitized[:100]

router = APIRouter(prefix="/tenants", tags=["Tenants"])


async def _is_system_admin(current_user: User, db: AsyncSession) -> bool:
    role_repo = RoleRepository(db)
    roles = await role_repo.get_user_roles(current_user.id)
    return RoleName.ADMIN.value in roles or RoleName.MODERATOR.value in roles


async def _enforce_tenant_scope(
    current_user: User, target_tenant_id: int, db: AsyncSession
) -> None:
    if await _is_system_admin(current_user, db):
        return
    if current_user.tenant_id is None or current_user.tenant_id != target_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "TENANT_FORBIDDEN",
                "message": "Cannot access a tenant you do not belong to.",
            },
        )


async def _load_tenant_user(
    tenant_id: int, user_id: UUID, db: AsyncSession
) -> User:
    target = await UserRepository(db).get_by_id(user_id)
    if not target:
        raise EntityNotFoundError(f"User {user_id}")
    if target.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_IN_TENANT", "message": "User does not belong to this tenant."},
        )
    return target


def _tenant_response(tenant: Tenant) -> dict:
    return TenantResponse.model_validate(tenant, from_attributes=True).model_dump(mode="json")


def _user_response(user: User) -> dict:
    return UserListResponse.model_validate(user, from_attributes=True).model_dump(mode="json")


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    auth_svc: AuthService = Depends(get_auth_service),
):
    """Create a tenant and auto-provision its first admin user.

    Atomic: tenant + user + verification token share the same DB session, so
    if user provisioning fails (duplicate email/username on the users table)
    the tenant insert is also rolled back.

    Side effect: a setup-link email is enqueued to the contact email so the
    contact can activate the admin account and log in. No separate
    informational email is sent &mdash; the setup-link is the entry point.
    """
    repo = TenantRepository(db)
    if await repo.get_by_email(body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "DUPLICATE_TENANT_EMAIL", "message": "A tenant with this email already exists."},
        )

    tenant = Tenant(
        name=body.name,
        organisation=body.organisation,
        email=body.email,
        phone_number=body.phone_number,
        status=TenantStatus.ACTIVATED,
        created_by=current_user.id,
    )
    await repo.create(tenant)  # flush only — tenant_id now populated

    # Auto-provision the first admin user for this tenant. The username is
    # derived from the email local part; if it collides, provision_user
    # raises DuplicateEntityError and the whole transaction rolls back.
    derived_username = _derive_username_from_email(body.email)
    await auth_svc.provision_user(
        email=body.email,
        username=derived_username,
        full_name=body.name,
        phone_number=body.phone_number,
        tenant_id=str(tenant.id),
        creation_type="tenant",
        role_name=Roles.TENANT_ADMIN,
        background_tasks=background_tasks,
    )

    # provision_user committed; refresh tenant to surface server-side defaults
    # (created_at, etc.) without re-querying.
    await db.refresh(tenant)

    return success_response(data=_tenant_response(tenant))


@router.get("")
async def list_tenants(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status_filter: Optional[TenantStatus] = Query(None, alias="status"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    repo = TenantRepository(db)
    if await _is_system_admin(current_user, db):
        tenants = await repo.list_all(offset=offset, limit=limit, status=status_filter)
    elif current_user.tenant_id is not None:
        own = await repo.get_by_id(current_user.tenant_id)
        tenants = [own] if own and (status_filter is None or own.status == status_filter) else []
    else:
        tenants = []
    return success_response(data=[_tenant_response(t) for t in tenants])


@router.get("/{tenant_id}")
async def get_tenant(
    tenant_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    await _enforce_tenant_scope(current_user, tenant_id, db)
    tenant = await TenantRepository(db).get_by_id(tenant_id)
    if not tenant:
        raise EntityNotFoundError(f"Tenant {tenant_id}")
    return success_response(data=_tenant_response(tenant))


@router.patch("/{tenant_id}")
async def update_tenant(
    tenant_id: int,
    body: TenantUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    repo = TenantRepository(db)
    tenant = await repo.get_by_id(tenant_id)
    if not tenant:
        raise EntityNotFoundError(f"Tenant {tenant_id}")
    data = body.model_dump(exclude_unset=True)
    # Status changes go through PATCH /status to keep authorization split clean.
    data.pop("status", None)
    data["updated_by"] = current_user.id
    await repo.update(tenant, data)
    await repo.save_and_refresh(tenant)
    return success_response(data=_tenant_response(tenant))


@router.patch("/{tenant_id}/status")
async def update_tenant_status(
    tenant_id: int,
    body: TenantStatusUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    repo = TenantRepository(db)
    tenant = await repo.get_by_id(tenant_id)
    if not tenant:
        raise EntityNotFoundError(f"Tenant {tenant_id}")
    await repo.update(
        tenant,
        {"status": body.status, "updated_by": current_user.id},
    )
    await repo.save_and_refresh(tenant)
    return success_response(data=_tenant_response(tenant))


@router.get("/{tenant_id}/users")
async def list_tenant_users(
    tenant_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    await _enforce_tenant_scope(current_user, tenant_id, db)
    users = await UserRepository(db).list_by_tenant(tenant_id, offset=offset, limit=limit)
    return success_response(data=[_user_response(u) for u in users])


@router.post("/{tenant_id}/users", status_code=status.HTTP_201_CREATED)
async def create_tenant_user(
    tenant_id: int,
    body: TenantUserCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    auth_svc: AuthService = Depends(get_auth_service),
):
    await _enforce_tenant_scope(current_user, tenant_id, db)

    if not await TenantRepository(db).get_by_id(tenant_id):
        raise EntityNotFoundError(f"Tenant {tenant_id}")

    user_id_str, setup_token = await auth_svc.provision_user(
        email=body.email,
        username=body.username,
        full_name=body.full_name,
        phone_number=body.phone_number,
        tenant_id=str(tenant_id),
        creation_type=CreationType.DEFAULT.value,
    )
    return success_response(
        data=TenantUserCreateResponse(user_id=user_id_str, setup_token=setup_token).model_dump()
    )


@router.patch("/{tenant_id}/users/{user_id}/status")
async def update_tenant_user_status(
    tenant_id: int,
    user_id: UUID,
    body: TenantUserStatusUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    await _enforce_tenant_scope(current_user, tenant_id, db)
    target = await _load_tenant_user(tenant_id, user_id, db)

    payload = body.model_dump(exclude_unset=True)
    payload["updated_by"] = current_user.id
    user_repo = UserRepository(db)
    await user_repo.update(target, payload)
    await user_repo.save_and_refresh(target)
    return success_response(data=_user_response(target))


@router.patch("/{tenant_id}/users/{user_id}")
async def update_tenant_user(
    tenant_id: int,
    user_id: UUID,
    body: TenantUserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    await _enforce_tenant_scope(current_user, tenant_id, db)
    target = await _load_tenant_user(tenant_id, user_id, db)

    payload = body.model_dump(exclude_unset=True)
    payload["updated_by"] = current_user.id
    user_repo = UserRepository(db)
    await user_repo.update(target, payload)
    await user_repo.save_and_refresh(target)
    return success_response(data=_user_response(target))


@router.delete("/{tenant_id}/users/{user_id}")
async def delete_tenant_user(
    tenant_id: int,
    user_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    await _enforce_tenant_scope(current_user, tenant_id, db)
    target = await _load_tenant_user(tenant_id, user_id, db)

    user_repo = UserRepository(db)
    await user_repo.update(
        target,
        {
            "is_delete": True,
            "is_active": False,
            "is_tenant_active": False,
            "updated_by": current_user.id,
        },
    )
    await user_repo.commit()
    return success_response(data={"user_id": str(user_id), "deleted": True})
