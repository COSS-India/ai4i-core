"""Usage Viewer recipients, read from ai4iplatform_auth at send time.

ai4i_core's RecipientResolver.for_roles honours only the MONITORING roles
(ADMIN / MODERATOR), so it can't resolve USAGE VIEWER; this is the same
role query (Q-R3) for that one role. users.email is encrypted at rest; a
user whose email fails to decrypt is skipped, as RecipientResolver does.
"""
from __future__ import annotations

import logging
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


async def usage_viewer_emails(
    auth_db: AsyncSession, decrypt_email: Callable[[Optional[str]], Optional[str]]
) -> list[str]:
    """Active Usage Viewers' emails, one per address (case-insensitive), sorted."""
    rows = (await auth_db.execute(_ROLE_USERS_SQL, {"role": USAGE_VIEWER_ROLE})).all()
    emails: dict[str, str] = {}
    for user_id, encrypted in rows:
        try:
            email = decrypt_email(encrypted)
        except Exception as exc:
            logger.warning("Skipping Usage Viewer %s: email failed to decrypt: %s", user_id, exc)
            continue
        if email:
            emails.setdefault(email.strip().lower(), email.strip())
    return sorted(emails.values(), key=str.lower)
