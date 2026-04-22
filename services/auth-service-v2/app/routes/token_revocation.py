"""
Admin token-revocation endpoints.

Bulk revokes refresh tokens in Redis for a given tenant or user set.
URL path retains `/sessions/...` for backwards compatibility — the
underlying implementation is pure token revocation, not DB sessions.
"""

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.responses import success_response
from app.dependencies.permissions import require_any_role
from app.dependencies.services import get_cache_service
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.cache_service import CacheService
from app.services.tenant_service import TenantService

router = APIRouter(prefix="/auth/sessions", tags=["Session Revocation"])


@router.post("/revoke-by-tenant/{tenant_id}")
async def revoke_sessions_by_tenant(
    request: Request,
    tenant_id: str = Path(
        ...,
        min_length=1,
        max_length=100,
        pattern=r".*\S.*",
        description="Tenant identifier",
    ),
    current_admin: User = Depends(require_any_role("ADMIN")),
    cache: CacheService = Depends(get_cache_service),
):
    mt_factory = getattr(request.app.state, "multi_tenant_session_factory", None)
    if not mt_factory:
        raise HTTPException(status_code=503, detail="Multi-tenant DB not configured in auth service")

    cooldown_scope = f"tenant:{tenant_id}"
    acquired = await cache.acquire_revocation_cooldown(
        cooldown_scope,
        settings.revocation_endpoint_cooldown_seconds,
    )
    if not acquired:
        retry_after = await cache.get_revocation_cooldown_ttl(cooldown_scope)
        raise HTTPException(
            status_code=429,
            detail={
                "message": "Session revocation for this tenant was requested too recently.",
                "retry_after_seconds": retry_after,
                "tenant_id": tenant_id,
                "requested_by": current_admin.id,
            },
        )

    tenant_service = TenantService(mt_factory)
    user_ids = await tenant_service.get_tenant_user_ids(tenant_id) or []
    if not user_ids:
        return success_response(data={
            "tenant_id": tenant_id,
            "users_matched": 0,
            "sessions_revoked": 0,
        })

    tokens_revoked = await cache.revoke_all_user_tokens(user_ids)
    await cache.delete_tenant_status(tenant_id)

    return success_response(data={
        "tenant_id": tenant_id,
        "users_matched": len(user_ids),
        "sessions_revoked": tokens_revoked,
    })


class RevokeSessionsByUsersRequest(BaseModel):
    user_ids: list[int]


@router.post("/revoke-by-users")
async def revoke_sessions_by_users(
    body: RevokeSessionsByUsersRequest,
    current_admin: User = Depends(require_any_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache_service),
):
    user_ids = sorted({int(uid) for uid in body.user_ids if uid is not None})
    if not user_ids:
        return success_response(data={"users_matched": 0, "sessions_revoked": 0})

    user_scope_hash = hashlib.sha256(",".join(map(str, user_ids)).encode("utf-8")).hexdigest()[:16]
    cooldown_scope = f"users:{user_scope_hash}"
    acquired = await cache.acquire_revocation_cooldown(
        cooldown_scope,
        settings.revocation_endpoint_cooldown_seconds,
    )
    if not acquired:
        retry_after = await cache.get_revocation_cooldown_ttl(cooldown_scope)
        raise HTTPException(
            status_code=429,
            detail={
                "message": "Session revocation for this user set was requested too recently.",
                "retry_after_seconds": retry_after,
                "users_matched": len(user_ids),
                "requested_by": current_admin.id,
            },
        )

    tokens_revoked = await cache.revoke_all_user_tokens(user_ids)

    tenant_ids = await UserRepository(db).get_distinct_tenant_ids_for_users(user_ids)
    for tid in tenant_ids:
        await cache.delete_tenant_status(tid)

    return success_response(data={
        "users_matched": len(user_ids),
        "sessions_revoked": tokens_revoked,
    })
