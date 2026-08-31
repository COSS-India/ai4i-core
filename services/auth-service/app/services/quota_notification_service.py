"""Quota notification service — sends transactional emails for pay-per-use quota events."""

import logging
from typing import List, Optional
from uuid import UUID

from ai4i_core.email import EmailClient
from fastapi import BackgroundTasks

from app.repositories.role_repository import RoleRepository
from app.repositories.tenant_repository import TenantRepository
from app.services.auth_email_templates import render_quota_limit_updated
from app.services.email_helpers import enqueue_email

logger = logging.getLogger(__name__)


class QuotaNotificationService:
    def __init__(
        self,
        role_repo: RoleRepository,
        email_client: EmailClient,
        tenant_repo: TenantRepository,
    ) -> None:
        self._role_repo = role_repo
        self._email_client = email_client
        self._tenant_repo = tenant_repo

    async def notify_quota_limit_updated(
        self,
        tier_name: str,
        tenant_ids: List[str],
        background_tasks: BackgroundTasks,
        tier_id: Optional[str] = None,
    ) -> None:
        """tier_id is now how the caller (platform-core-service) identifies
        which tenants to notify — it no longer has a DB of its own to
        compute tenant_ids from (ppu_tenant_tier_assignments is dropped),
        so it hands over the tier and this resolves the live assignment
        from tenants.tier_id itself. The passed-in ``tenant_ids`` is used
        as-is only when ``tier_id`` is absent, for a rolling-deploy window
        against an older caller that still sends only tenant_ids (see
        QuotaLimitUpdatedRequest)."""
        if tier_id is not None:
            try:
                tier_uuid = UUID(tier_id)
            except ValueError:
                logger.error("quota-limit-updated: invalid tier_id %r", tier_id)
                tier_uuid = None
            tenant_ids = (
                [str(t.id) for t in await self._tenant_repo.list_with_tier(tier_uuid)]
                if tier_uuid is not None
                else []
            )

        for tenant_id in tenant_ids:
            if not tenant_id.isdigit():
                logger.error(
                    "quota-limit-updated: skipping tenant %r — non-numeric id", tenant_id
                )
                continue
            try:
                admins = await self._role_repo.get_tenant_admins(int(tenant_id))
                for admin in admins:
                    enqueue_email(
                        background_tasks,
                        self._email_client,
                        lambda u=admin, t=tier_name: render_quota_limit_updated(u, t),
                    )
            except Exception as exc:
                logger.warning(
                    "quota-limit-updated: failed to notify tenant %s: %s", tenant_id, exc
                )
