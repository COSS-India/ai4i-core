"""Producer-side recipient resolution — who actually gets a notification.

Previously the consumer (notifications_consumer/recipients.py) resolved
this itself, from configs_notification_alert.recipient_roles, at delivery
time. That column is gone (see e2a4c6b8d0f2_add_scope_drop_recipient_roles_
notification_catalog.py) — scope now decides only whether an event fires at
all, not who receives it. Who receives it is resolved HERE, once, by the
producer, before the event is ever published, and travels with the message
as a plain list of email addresses (publish_event's ``recipients``
parameter) — the consumer just sends to that list, it no longer queries
anything to figure out who to notify.

Every event still goes to this tenant's ADMIN (platform-wide) + TENANT
ADMIN (this tenant) users, unconditionally — the same two roles every
catalog row was always restricted to (catalog_metadata.LEGAL_RECIPIENT_ROLES,
now removed since it never varied). On top of that fixed set, an
INSTITUTION-scope row's tenant can name additional recipients via
tenant_notification_subscription.recipients (a list of that tenant's own
user ids, validated at write time by subscription_service) — those are
included regardless of the row's current scope, so recipients added while a
row was INSTITUTION-scope survive a later revert to GLOBAL (see that
table's own docstring).

users.email is encrypted at rest — configure(decrypt_email) once at service
startup with that service's own decrypt function (each service already has
its own pii_crypto module/key, there's no one shared instance), mirroring
notification_settings_cache's own module-level state pattern.
"""
import logging
from typing import Callable, Dict, List, Optional, Tuple

from sqlalchemy import text

logger = logging.getLogger(__name__)

_decrypt_email: Optional[Callable[[Optional[str]], Optional[str]]] = None


def configure(decrypt_email: Callable[[Optional[str]], Optional[str]]) -> None:
    """Set the decrypt function this module calls on every users.email it
    reads. Must be called once at service startup, before
    resolve_recipients() is ever called."""
    global _decrypt_email
    _decrypt_email = decrypt_email


def _decrypt(token: Optional[str]) -> Optional[str]:
    if _decrypt_email is None:
        raise RuntimeError("ai4i_core.kafka.recipients.configure(decrypt_email) was not called")
    return _decrypt_email(token)


async def _role_based_emails(auth_db, tenant_id: str) -> List[str]:
    """This tenant's ADMIN (platform-wide) + TENANT ADMIN users — the fixed
    baseline every notification has always gone to. Same join shape as the
    old notifications_consumer/recipients.py::resolve(roles=["ADMIN",
    "TENANT ADMIN"]) — ADMIN is exempt from the tenant filter since it's a
    platform-wide role, not scoped to any one tenant."""
    result = await auth_db.execute(
        text(
            "SELECT DISTINCT u.email"
            "  FROM users u"
            "  JOIN user_role ur ON ur.user_id = u.id"
            "  JOIN roles r ON r.id = ur.role_id"
            " WHERE r.name = ANY(:roles)"
            "   AND (r.name = 'ADMIN' OR u.tenant_id = :tenant_id)"
            "   AND u.is_delete IS NOT TRUE"
            "   AND u.is_active IS TRUE"
        ),
        {"roles": ["ADMIN", "TENANT ADMIN"], "tenant_id": int(tenant_id)},
    )
    return [row.email for row in result.all()]


async def _extra_recipient_emails(core_db, auth_db, notification_id: int, tenant_id: str) -> List[str]:
    """This tenant's additional recipients for this notification —
    tenant_notification_subscription.recipients is a list of user ids
    (validated against this tenant's own users at write time), resolved to
    emails here. A missing subscription row (never opted in / created after
    the seed) has nothing extra to add."""
    sub_result = await core_db.execute(
        text(
            "SELECT recipients FROM tenant_notification_subscription"
            " WHERE notification_id = :notification_id AND tenant_id = :tenant_id"
        ),
        {"notification_id": notification_id, "tenant_id": str(tenant_id)},
    )
    row = sub_result.first()
    user_ids = list(row.recipients or []) if row is not None else []
    if not user_ids:
        return []

    result = await auth_db.execute(
        text(
            "SELECT email FROM users"
            " WHERE tenant_id = :tenant_id"
            "   AND is_delete IS NOT TRUE"
            "   AND is_active IS TRUE"
            "   AND id::text = ANY(:user_ids)"
        ),
        {"tenant_id": int(tenant_id), "user_ids": user_ids},
    )
    return [row.email for row in result.all()]


async def resolve_recipients(
    core_db, auth_db, *, notification_id: int, tenant_id: str
) -> List[str]:
    """The full, deduplicated, decrypted email list for one (notification,
    tenant) — this tenant's ADMIN/TENANT ADMIN users, plus its own
    additional recipients on file, if any.

    core_db is the session against whichever database holds
    configs_notification_alert/tenant_notification_subscription
    (ai4iplatform_core); auth_db is the session against ai4iplatform_auth,
    where users/roles actually live. Best-effort: a lookup failure here
    must never break the event it's resolving recipients for — returns []
    (the event still publishes, ledger-recorded as fired; delivery.py's own
    "no_recipients" outcome is what surfaces this, not an exception here)."""
    try:
        encrypted = set(await _role_based_emails(auth_db, tenant_id))
        encrypted.update(await _extra_recipient_emails(core_db, auth_db, notification_id, tenant_id))
    except Exception as exc:
        logger.warning(
            "Recipient resolution failed for notification_id=%s tenant_id=%s: %s",
            notification_id, tenant_id, exc,
        )
        return []

    emails: List[str] = []
    for token in encrypted:
        try:
            email = _decrypt(token)
        except Exception as exc:
            logger.warning(
                "Skipping recipient that failed to decrypt (notification_id=%s tenant_id=%s): %s",
                notification_id, tenant_id, exc,
            )
            continue
        if email:
            emails.append(email)
        else:
            logger.warning("Skipping recipient with no decryptable email (notification_id=%s tenant_id=%s)",
                            notification_id, tenant_id)
    return sorted(emails)


async def _role_based_emails_bulk(auth_db, tenant_ids: List[str]) -> Tuple[List[str], Dict[str, List[str]]]:
    """Bulk sibling of _role_based_emails for many tenants at once: the
    platform ADMIN list is the same for every tenant, so it's fetched once;
    TENANT ADMIN users are fetched in a single tenant_id = ANY(...) query and
    grouped by tenant. Used by a fan-out that touches every tenant on a tier
    (a tier PATCH), where one query per tenant would otherwise add hundreds
    of round trips."""
    admin_result = await auth_db.execute(
        text(
            "SELECT DISTINCT u.email"
            "  FROM users u"
            "  JOIN user_role ur ON ur.user_id = u.id"
            "  JOIN roles r ON r.id = ur.role_id"
            " WHERE r.name = 'ADMIN'"
            "   AND u.is_delete IS NOT TRUE"
            "   AND u.is_active IS TRUE"
        )
    )
    admin_emails = [row.email for row in admin_result.all()]

    tenant_admin_result = await auth_db.execute(
        text(
            "SELECT u.tenant_id, u.email"
            "  FROM users u"
            "  JOIN user_role ur ON ur.user_id = u.id"
            "  JOIN roles r ON r.id = ur.role_id"
            " WHERE r.name = 'TENANT ADMIN'"
            "   AND u.tenant_id::text = ANY(:tenant_ids)"
            "   AND u.is_delete IS NOT TRUE"
            "   AND u.is_active IS TRUE"
        ),
        {"tenant_ids": tenant_ids},
    )
    tenant_admin_emails: Dict[str, List[str]] = {}
    for row in tenant_admin_result.all():
        tenant_admin_emails.setdefault(str(row.tenant_id), []).append(row.email)
    return admin_emails, tenant_admin_emails


async def _extra_recipient_emails_bulk(
    core_db, auth_db, notification_id: int, tenant_ids: List[str]
) -> Dict[str, List[str]]:
    """Bulk sibling of _extra_recipient_emails: one subscription-table query
    and one users query for every tenant in tenant_ids, instead of one pair
    per tenant."""
    sub_result = await core_db.execute(
        text(
            "SELECT tenant_id, recipients FROM tenant_notification_subscription"
            " WHERE notification_id = :notification_id AND tenant_id = ANY(:tenant_ids)"
        ),
        {"notification_id": notification_id, "tenant_ids": tenant_ids},
    )
    user_ids_by_tenant: Dict[str, List[str]] = {}
    all_user_ids: List[str] = []
    for row in sub_result.all():
        ids = list(row.recipients or [])
        if ids:
            user_ids_by_tenant[str(row.tenant_id)] = ids
            all_user_ids.extend(ids)
    if not all_user_ids:
        return {}

    users_result = await auth_db.execute(
        text(
            "SELECT id, tenant_id, email FROM users"
            " WHERE tenant_id::text = ANY(:tenant_ids)"
            "   AND is_delete IS NOT TRUE"
            "   AND is_active IS TRUE"
            "   AND id::text = ANY(:user_ids)"
        ),
        {"tenant_ids": tenant_ids, "user_ids": all_user_ids},
    )
    # Keyed by (tenant_id, user_id) rather than user_id alone, so a
    # recipient id that (incorrectly) matches a user in another tenant can
    # never leak across tenants here.
    email_by_tenant_user: Dict[Tuple[str, str], str] = {
        (str(row.tenant_id), str(row.id)): row.email for row in users_result.all()
    }

    extra_by_tenant: Dict[str, List[str]] = {}
    for tenant_id, user_ids in user_ids_by_tenant.items():
        emails = [
            email_by_tenant_user[(tenant_id, uid)]
            for uid in user_ids
            if (tenant_id, uid) in email_by_tenant_user
        ]
        if emails:
            extra_by_tenant[tenant_id] = emails
    return extra_by_tenant


async def resolve_recipients_bulk(
    core_db, auth_db, *, notification_id: int, tenant_ids: List[str]
) -> Dict[str, List[str]]:
    """Bulk sibling of resolve_recipients: the same per-tenant recipient set
    (ADMIN + TENANT ADMIN + extra subscribed recipients), but for every
    tenant in tenant_ids using a fixed number of queries instead of one set
    of queries per tenant — for a fan-out like a tier PATCH that can touch
    hundreds of tenants at once. Best-effort per tenant, same as
    resolve_recipients: a tenant that isn't in the returned dict, or that
    fails entirely, gets []."""
    tenant_ids = [str(t) for t in tenant_ids]
    if not tenant_ids:
        return {}
    try:
        admin_emails, tenant_admin_emails = await _role_based_emails_bulk(auth_db, tenant_ids)
        extra_emails = await _extra_recipient_emails_bulk(core_db, auth_db, notification_id, tenant_ids)
    except Exception as exc:
        logger.warning(
            "Bulk recipient resolution failed for notification_id=%s tenant_ids=%s: %s",
            notification_id, tenant_ids, exc,
        )
        return {}

    result: Dict[str, List[str]] = {}
    for tenant_id in tenant_ids:
        encrypted = set(admin_emails)
        encrypted.update(tenant_admin_emails.get(tenant_id, []))
        encrypted.update(extra_emails.get(tenant_id, []))
        emails: List[str] = []
        for token in encrypted:
            try:
                email = _decrypt(token)
            except Exception as exc:
                logger.warning(
                    "Skipping recipient that failed to decrypt (notification_id=%s tenant_id=%s): %s",
                    notification_id, tenant_id, exc,
                )
                continue
            if email:
                emails.append(email)
        result[tenant_id] = sorted(emails)
    return result
