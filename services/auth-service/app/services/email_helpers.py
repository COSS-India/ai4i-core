"""Shared helpers for email and tenant-user operations."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from ai4icore_core.email import EmailClient, EmailMessage
from fastapi import BackgroundTasks

from app.core.config import settings
from app.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


def enqueue_email(
    background_tasks: Optional[BackgroundTasks],
    email_client: EmailClient,
    factory: Callable[[], EmailMessage],
) -> None:
    """Render and enqueue a send_safe call.

    ``factory`` is a zero-arg callable that returns an EmailMessage. Render
    is wrapped in try/except so a template/URL bug never 5xx's a request
    whose DB commit already succeeded — orphan-row prevention. Render
    failures are logged at ERROR for ops to catch via metrics.

    No-op when no BackgroundTasks available (e.g. tests calling the
    service directly without a request) — logged at WARN so production
    misuse is visible instead of silently dropping the email.
    """
    if background_tasks is None:
        logger.warning(
            "enqueue_email skipped: background_tasks is None; "
            "email would not be delivered"
        )
        return
    try:
        message = factory()
    except Exception:
        logger.exception("email render failed")
        return
    background_tasks.add_task(email_client.send_safe, message)


def setup_token_expires_at() -> datetime:
    """Calculate the expiration time for a setup token."""
    return datetime.now(timezone.utc) + timedelta(hours=settings.setup_token_expire_hours)


async def persist_token_verification(
    verification_repo,
    token: str,
    user_id,
    expires_at: datetime,
) -> "TokenVerification":
    """Create and persist a token verification record.

    Caller specifies expires_at to handle different TTL requirements:
    - setup/verify/resend_setup: setup_token_expire_hours (48h)
    - reset: reset_token_expire_minutes (30 min)
    """
    from app.models.verification import TokenVerification

    obj = TokenVerification(
        token=token,
        is_active=True,
        expires_at=expires_at,
        created_by=user_id,
    )
    await verification_repo.create(obj)
    return obj


async def issue_session(
    user,
    roles_svc,
    tokens_svc,
    refresh_tokens_repo,
    users_repo,
) -> "LoginResponse":
    """Issue JWT pair and persist refresh token. Used by both /auth/login and OAuth callback.

    Returns LoginResponse object (caller wraps with .model_dump() if needed).
    """
    from app.schemas.auth import LoginResponse

    tenant_id = str(user.tenant_id) if user.tenant_id else None
    permission_ids = await roles_svc.get_user_permission_ids(user.id)

    access_token = tokens_svc.create_access_token(
        user_id=str(user.id),
        tenant_id=tenant_id,
        permission_ids=permission_ids,
    )
    refresh_token = tokens_svc.create_refresh_token(
        user_id=str(user.id),
        tenant_id=tenant_id,
    )

    await refresh_tokens_repo.upsert(user.id, refresh_token)
    user.last_login = datetime.now(timezone.utc)
    await users_repo.commit()

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )


async def resolve_tenant_id(explicit: Optional[int | str], tenant_repo) -> Optional[int]:
    """Honor an explicit tenant_id, otherwise fall back to the default tenant.

    If an explicit tenant_id is provided, validates that the tenant exists.
    """
    if explicit is not None:
        try:
            tenant_id = int(explicit)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                message="Invalid tenant_id.",
                code="INVALID_TENANT_ID",
                errors=[f"tenant_id must be an integer, got: {explicit!r}"],
            ) from exc

        # Validate that the tenant exists
        tenant = await tenant_repo.get_by_id(tenant_id)
        if tenant is None:
            raise ValidationError(
                message="Tenant not found.",
                code="TENANT_NOT_FOUND",
                errors=[f"Tenant with ID {tenant_id} does not exist"],
            )
        return tenant_id

    # No explicit tenant_id: fall back to default tenant
    default = await tenant_repo.get_by_organisation(settings.default_tenant_org)
    if default is None:
        logger.warning(
            "Default tenant '%s' not found; user will be created without a tenant_id.",
            settings.default_tenant_org,
        )
        return None
    return default.id
