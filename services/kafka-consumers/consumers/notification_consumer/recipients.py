"""Resolves which real people hold a given set of roles for a tenant, by
reading ai4iplatform_auth directly — a second, named connection opened once
at startup (see main.py, bootstrap.lifecycle.add_database).

Raw SQL, not auth-service's ORM models — this is a different service/
codebase, same cross-service convention payperuse_consumer already uses for
platform-core's own tables (see _billing.py). Mirrors
RoleRepository.get_tenant_admins' shape (roles/user_role/users, filtered on
tenant_id + active + non-deleted), generalised to an arbitrary role list.

users.email is encrypted at rest — see pii_crypto.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ai4i_core.logging import get_logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from consumers.notification_consumer import pii_crypto

logger = get_logger(__name__)


@dataclass(frozen=True)
class Recipient:
    user_id: str
    email: str
    display_name: str


async def resolve(db: AsyncSession, *, tenant_id: str, roles: List[str]) -> List[Recipient]:
    """Active, non-deleted users under tenant_id holding any of `roles`.
    Empty `roles` or a non-numeric tenant_id (users.tenant_id is an integer
    FK) both resolve to no recipients rather than raising."""
    if not roles:
        return []
    if not tenant_id.isdigit():
        logger.error("resolve(): non-numeric tenant_id=%r — no recipients", tenant_id)
        return []

    result = await db.execute(
        text(
            "SELECT DISTINCT u.id, u.email, u.full_name"
            "  FROM users u"
            "  JOIN user_role ur ON ur.user_id = u.id"
            "  JOIN roles r ON r.id = ur.role_id"
            " WHERE r.name = ANY(:roles)"
            "   AND u.tenant_id = :tenant_id"
            "   AND u.is_delete IS NOT TRUE"
            "   AND u.is_active IS TRUE"
        ),
        {"roles": roles, "tenant_id": int(tenant_id)},
    )

    recipients = []
    for user_id, encrypted_email, full_name in result.all():
        email = pii_crypto.decrypt_email(encrypted_email)
        if not email:
            logger.warning("Skipping recipient %s — no decryptable email", user_id)
            continue
        recipients.append(
            Recipient(user_id=str(user_id), email=email, display_name=full_name or "there")
        )
    return recipients
