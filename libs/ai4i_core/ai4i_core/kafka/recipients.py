"""Recipient resolution, ai4iplatform_auth (Q-R1, Q-R2, Q-R3).

Runs only when an event fires. Role flags come from the settings row's
recipient_roles; extra user ids come from the tenant's own subscription row,
and are only ever matched inside that tenant. users.email is encrypted at
rest and decrypted in-process; a recipient that fails to decrypt is skipped.
"""

import logging
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import text

from .constants import RecipientRole
from .models import Recipient

logger = logging.getLogger(__name__)

DecryptEmail = Callable[[Optional[str]], Optional[str]]

# Q-R1 — recipients of one tenant, plus the institution name
_ONE_TENANT_SQL = text(
    """
    SELECT DISTINCT u.id, u.email, u.full_name,
           (SELECT t.name FROM tenants t WHERE t.id = :tenant_id) AS tenant_name
      FROM users u
      LEFT JOIN user_role ur ON ur.user_id = u.id
      LEFT JOIN roles r      ON r.id = ur.role_id
     WHERE u.is_active IS TRUE
       AND u.is_delete IS NOT TRUE
       AND (    (:include_admin        AND r.name = :admin_role)
             OR (:include_tenant_admin AND r.name = :tenant_admin_role
                                       AND u.tenant_id = :tenant_id)
             OR (u.tenant_id = :tenant_id
                 AND u.id::text = ANY(CAST(:extra_user_ids AS varchar[]))) )
    """
)

# Q-R2 — recipients of many tenants, grouped per tenant in code
_MANY_TENANTS_SQL = text(
    """
    SELECT u.tenant_id::text AS tenant_id, r.name AS role, u.id::text AS user_id,
           u.email, u.full_name
      FROM users u
      LEFT JOIN user_role ur ON ur.user_id = u.id
      LEFT JOIN roles r      ON r.id = ur.role_id
     WHERE u.is_active IS TRUE
       AND u.is_delete IS NOT TRUE
       AND (    (:include_admin        AND r.name = :admin_role)
             OR (:include_tenant_admin AND r.name = :tenant_admin_role
                                       AND u.tenant_id::text = ANY(CAST(:tenant_ids AS varchar[])))
             OR (u.tenant_id::text = ANY(CAST(:tenant_ids AS varchar[]))
                 AND u.id::text = ANY(CAST(:extra_user_ids AS varchar[]))) )
    """
)

# Q-R3 — monitoring recipients, ids from the settings snapshot
_USERS_SQL = text(
    """
    SELECT id, email, full_name
      FROM users
     WHERE id::text = ANY(CAST(:user_ids AS varchar[]))
       AND is_active IS TRUE
       AND is_delete IS NOT TRUE
    """
)


class RecipientResolver:
    def __init__(self, decrypt_email: DecryptEmail):
        self._decrypt = decrypt_email

    def _recipient(self, encrypted: Optional[str], full_name: Optional[str]) -> Optional[Recipient]:
        try:
            email = self._decrypt(encrypted)
        except Exception as exc:
            logger.warning("Skipping a notification recipient whose email failed to decrypt: %s", exc)
            return None
        return Recipient(email=email, name=full_name or "") if email else None

    def _unique(self, rows: Iterable[Tuple[str, Optional[str], Optional[str]]]) -> List[Recipient]:
        """(user_id, encrypted email, full_name) rows -> recipients, one per
        user, sorted by email."""
        seen: Dict[str, Recipient] = {}
        for user_id, encrypted, full_name in rows:
            if user_id in seen:
                continue
            recipient = self._recipient(encrypted, full_name)
            if recipient is not None:
                seen[user_id] = recipient
        return sorted(seen.values(), key=lambda r: r.email)

    async def for_tenant(
        self,
        session,
        tenant_id: str,
        recipient_roles: Mapping[str, bool],
        extra_user_ids: Sequence[str] = (),
    ) -> Tuple[List[Recipient], Optional[str]]:
        """Q-R1: recipients of one tenant and the institution name."""
        result = await session.execute(
            _ONE_TENANT_SQL,
            {
                "tenant_id": int(tenant_id),
                "include_admin": bool(recipient_roles.get(RecipientRole.ADMIN.value)),
                "include_tenant_admin": bool(recipient_roles.get(RecipientRole.TENANT_ADMIN.value)),
                "admin_role": RecipientRole.ADMIN.value,
                "tenant_admin_role": RecipientRole.TENANT_ADMIN.value,
                "extra_user_ids": [str(u) for u in extra_user_ids],
            },
        )
        rows = result.mappings().all()
        tenant_name = rows[0]["tenant_name"] if rows else None
        return self._unique((str(r["id"]), r["email"], r["full_name"]) for r in rows), tenant_name

    async def for_tenants(
        self,
        session,
        tenant_ids: Sequence[str],
        recipient_roles: Mapping[str, bool],
        extra_user_ids: Mapping[str, Sequence[str]],
    ) -> Dict[str, List[Recipient]]:
        """Q-R2: recipients of many tenants. ADMIN users go to every tenant; a
        TENANT ADMIN only to their own tenant; an extra user id only to the
        tenant whose subscription lists it."""
        ids = [str(t) for t in tenant_ids]
        if not ids:
            return {}
        include_admin = bool(recipient_roles.get(RecipientRole.ADMIN.value))
        include_tenant_admin = bool(recipient_roles.get(RecipientRole.TENANT_ADMIN.value))
        extras = {str(t): {str(u) for u in users} for t, users in extra_user_ids.items()}
        result = await session.execute(
            _MANY_TENANTS_SQL,
            {
                "tenant_ids": ids,
                "include_admin": include_admin,
                "include_tenant_admin": include_tenant_admin,
                "admin_role": RecipientRole.ADMIN.value,
                "tenant_admin_role": RecipientRole.TENANT_ADMIN.value,
                "extra_user_ids": sorted({u for users in extras.values() for u in users}),
            },
        )
        admins: List[Tuple[str, Optional[str], Optional[str]]] = []
        per_tenant: Dict[str, List[Tuple[str, Optional[str], Optional[str]]]] = {t: [] for t in ids}
        for row in result.mappings():
            entry = (row["user_id"], row["email"], row["full_name"])
            tenant = row["tenant_id"]
            if include_admin and row["role"] == RecipientRole.ADMIN.value:
                admins.append(entry)
            if tenant in per_tenant:
                if include_tenant_admin and row["role"] == RecipientRole.TENANT_ADMIN.value:
                    per_tenant[tenant].append(entry)
                if row["user_id"] in extras.get(tenant, ()):
                    per_tenant[tenant].append(entry)
        return {tenant: self._unique(admins + rows) for tenant, rows in per_tenant.items()}

    async def for_users(self, session, user_ids: Sequence[str]) -> List[Recipient]:
        """Q-R3: recipients by user id (monitoring)."""
        if not user_ids:
            return []
        result = await session.execute(_USERS_SQL, {"user_ids": [str(u) for u in user_ids]})
        return self._unique((str(r["id"]), r["email"], r["full_name"]) for r in result.mappings())
