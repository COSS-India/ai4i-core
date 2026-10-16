"""Usage Viewer recipients, read from ai4iplatform_auth at send time.

ai4i_core's RecipientResolver.for_roles honours only the MONITORING roles
(ADMIN / MODERATOR), so it can't resolve USAGE VIEWER; this is the same
role query (Q-R3) for that one role. users.email is encrypted at rest; a
user whose email fails to decrypt is skipped, as RecipientResolver does.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

USAGE_VIEWER_ROLE = "USAGE VIEWER"

_ROLE_USERS_SQL = text(
    """
    SELECT DISTINCT u.id, u.email
      FROM users u
      JOIN user_role ur ON ur.user_id = u.id
      JOIN roles r      ON r.id = ur.role_id
     WHERE r.name = :role
       AND u.is_active IS TRUE
       AND u.is_delete IS NOT TRUE
    """
)


@dataclass(frozen=True)
class Recipient:
    user_id: str
    email: str


async def usage_viewers(
    auth_db: AsyncSession, decrypt_email: Callable[[Optional[str]], Optional[str]]
) -> list[Recipient]:
    """Active Usage Viewers, one per address (case-insensitive), sorted by email.
    Two accounts sharing an address get one email, logged under the first id."""
    rows = (await auth_db.execute(_ROLE_USERS_SQL, {"role": USAGE_VIEWER_ROLE})).all()
    by_email: dict[str, Recipient] = {}
    for user_id, encrypted in rows:
        try:
            email = decrypt_email(encrypted)
        except Exception as exc:
            logger.warning("Skipping Usage Viewer %s: email failed to decrypt: %s", user_id, exc)
            continue
        if email:
            by_email.setdefault(email.strip().lower(), Recipient(str(user_id), email.strip()))
    return sorted(by_email.values(), key=lambda r: r.email.lower())


async def usage_viewer_emails(
    auth_db: AsyncSession, decrypt_email: Callable[[Optional[str]], Optional[str]]
) -> list[str]:
    """Active Usage Viewers' emails, one per address (case-insensitive), sorted."""
    return [r.email for r in await usage_viewers(auth_db, decrypt_email)]
