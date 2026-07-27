"""PPU notification service — sends transactional emails for pay-per-use events."""

import logging
from typing import List

from ai4i_core.email import EmailClient
from fastapi import BackgroundTasks

from app.repositories.role_repository import RoleRepository
from app.services.auth_email_templates import render_quota_limit_updated
from app.services.email_helpers import enqueue_email

logger = logging.getLogger(__name__)


class PPUNotificationService:
    def __init__(self, role_repo: RoleRepository, email_client: EmailClient) -> None:
        self._role_repo = role_repo
        self._email_client = email_client

    async def notify_quota_limit_updated(
        self,
        tier_name: str,
        tenant_ids: List[str],
        background_tasks: BackgroundTasks,
    ) -> None:
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
