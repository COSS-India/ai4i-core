"""Shared helpers for email and tenant-user operations."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from ai4icore_email import EmailClient, EmailMessage
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


async def resolve_tenant_id(explicit: Optional[int | str], tenant_repo) -> Optional[int]:
    """Honor an explicit tenant_id, otherwise fall back to the default tenant."""
    if explicit is not None:
        try:
            return int(explicit)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                message="Invalid tenant_id.",
                code="INVALID_TENANT_ID",
                errors=[f"tenant_id must be an integer, got: {explicit!r}"],
            ) from exc
    default = await tenant_repo.get_by_organisation(settings.default_tenant_org)
    if default is None:
        logger.warning(
            "Default tenant '%s' not found; user will be created without a tenant_id.",
            settings.default_tenant_org,
        )
        return None
    return default.id
