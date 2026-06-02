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

    Silent no-op when no BackgroundTasks available (e.g. tests calling the
    service directly without a request).
    """
    if background_tasks is None:
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


async def reissue_setup_token(
    user,
    *,
    credentials_repo,
    verifications_repo,
    token_service,
    background_tasks: Optional[BackgroundTasks],
) -> Optional[str]:
    """Invalidate ``user``'s outstanding SETUP tokens and mint a new one.

    Returns the new setup-token string on success, ``None`` when skipped —
    either because no ``BackgroundTasks`` was supplied (no way to deliver the
    email) or because the user already has credentials (onboarding complete).

    The helper deliberately does NOT commit and does NOT enqueue the email.
    Two reasons:

      1. Atomicity. Callers (``AuthService.resend_setup_link`` and the tenant
         email-update flow) often batch the new token row with related writes
         in the same transaction (e.g. updating ``users.email``). Committing
         here would split that transaction in two.
      2. Email-after-commit ordering. The activation email contains the token
         string. If the helper enqueued the email and the caller's later
         commit failed, the recipient would receive a link pointing at a
         token that doesn't exist in the DB. Returning the token lets the
         caller commit first and only then call ``enqueue_email`` with a
         ``lambda: render_setup_link(user, token)``.

    Token deactivation is scoped to ``TokenType.SETUP`` so unrelated VERIFY
    and RESET tokens for the same user are left alone.
    """
    # Local imports to avoid a circular dep (auth_email_templates imports
    # app.core.config which transitively imports this module on some setups).
    from app.core.constants import TokenType

    if background_tasks is None:
        logger.warning(
            "reissue_setup_token skipped: background_tasks is None; "
            "no way to deliver the email (user id=%s)", user.id,
        )
        return None

    existing_creds = await credentials_repo.get_by_user_id(user.id)
    if existing_creds:
        logger.info(
            "reissue_setup_token skipped: user id=%s already has credentials",
            user.id,
        )
        return None

    await verifications_repo.deactivate_all_for_user(
        str(user.id), token_type=TokenType.SETUP
    )

    setup_token = token_service.create_setup_token(
        user_id=str(user.id), email=user.email
    )
    await persist_token_verification(
        verifications_repo, setup_token, user.id, setup_token_expires_at()
    )
    return setup_token


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
