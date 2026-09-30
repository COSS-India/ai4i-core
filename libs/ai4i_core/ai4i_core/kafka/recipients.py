"""Recipient resolution, ai4iplatform_auth (Q-R1, Q-R2, Q-R3).

Monitoring recipients are not stored: Q-R3 resolves every active user who
holds a selected role (ADMIN / MODERATOR) at send time.

Runs only when an event fires. For a GLOBAL/INSTITUTION row (Q-R1/Q-R2), who
gets it is decided by scope, not a stored role flag: GLOBAL always resolves
every platform ADMIN plus this tenant's own TENANT ADMIN users; INSTITUTION
resolves only this tenant's own TENANT ADMIN users (the platform ADMIN is
deliberately excluded — an Institution-scope row is never delivered to the
Adopter Admin as such). Either way, the tenant's own extra recipients (its
subscription row's own added user ids) are always included on top, and are
only ever matched inside that tenant — recipients added while a row was
INSTITUTION-scope survive a later revert to GLOBAL.

users.email is encrypted at rest and decrypted in-process; a recipient that
fails to decrypt is skipped.
"""

import logging
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import text

from .constants import MONITORING_RECIPIENT_ROLES, NotificationScope, RecipientRole
from .models import Recipient

logger = logging.getLogger(__name__)

DecryptEmail = Callable[[Optional[str]], Optional[str]]

# Q-R1 — recipients of one tenant, plus the institution name. The name is
# tenants.organisation (the institution); tenants.name is the contact person.
_ONE_TENANT_SQL = text(
    """
    SELECT DISTINCT u.id, u.email, u.full_name,
           (SELECT t.organisation FROM tenants t WHERE t.id = :tenant_id) AS tenant_name
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

# Q-R3 — monitoring recipients: every active user holding a selected role,
# resolved at send time (no tenant filter; monitoring is platform-level)
_ROLE_USERS_SQL = text(
    """
    SELECT DISTINCT u.id, u.email, u.full_name
      FROM users u
      JOIN user_role ur ON ur.user_id = u.id
      JOIN roles r      ON r.id = ur.role_id
     WHERE r.name = ANY(CAST(:roles AS varchar[]))
       AND u.is_active IS TRUE
       AND u.is_delete IS NOT TRUE
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
        scope: NotificationScope,
        extra_user_ids: Sequence[str] = (),
    ) -> Tuple[List[Recipient], Optional[str]]:
        """Q-R1: recipients of one tenant and the institution name. GLOBAL
        includes every platform ADMIN; INSTITUTION never does (the Adopter
        Admin is not a recipient of an Institution-scope row). Both include
        this tenant's own TENANT ADMIN users and its extra recipients."""
        params = {
            "tenant_id": int(tenant_id),
            "include_admin": scope is NotificationScope.GLOBAL,
            "include_tenant_admin": True,
            "admin_role": RecipientRole.ADMIN.value,
            "tenant_admin_role": RecipientRole.TENANT_ADMIN.value,
            "extra_user_ids": [str(u) for u in extra_user_ids],
        }
        result = await session.execute(_ONE_TENANT_SQL, params)
        rows = result.mappings().all()
        tenant_name = rows[0]["tenant_name"] if rows else None
        return self._unique((str(r["id"]), r["email"], r["full_name"]) for r in rows), tenant_name

    async def for_tenants(
        self,
        session,
        tenant_ids: Sequence[str],
        scope: NotificationScope,
        extra_user_ids: Mapping[str, Sequence[str]],
    ) -> Dict[str, List[Recipient]]:
        """Q-R2: recipients of many tenants. GLOBAL: every platform ADMIN
        goes to every tenant, plus each tenant's own TENANT ADMIN users.
        INSTITUTION: no platform ADMIN, only each tenant's own TENANT ADMIN
        users. Either way, an extra user id only goes to the tenant whose
        subscription lists it."""
        ids = [str(t) for t in tenant_ids]
        if not ids:
            return {}
        include_admin = scope is NotificationScope.GLOBAL
        include_tenant_admin = True
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

    async def for_roles(self, session, roles: Sequence[str]) -> List[Recipient]:
        """Q-R3: monitoring recipients, resolved now from the selected roles,
        so a user granted, revoked or deactivated since the last save is
        reflected on the next alert. Only MONITORING roles are honoured."""
        legal = {r.value for r in MONITORING_RECIPIENT_ROLES}
        selected = sorted({str(r) for r in roles} & legal)
        if not selected:
            return []
        result = await session.execute(_ROLE_USERS_SQL, {"roles": selected})
        return self._unique((str(r["id"]), r["email"], r["full_name"]) for r in result.mappings())
