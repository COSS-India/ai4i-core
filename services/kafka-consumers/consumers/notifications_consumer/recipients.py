"""institution_name lookup for the email body, by reading ai4iplatform_auth
directly — a second, named connection opened once at startup (see main.py,
bootstrap.lifecycle.add_database).

Used to also resolve WHICH people get an email (resolve(), from
configs_notification_alert.recipient_roles) — that column still exists
(platform-core's e2a4c6b8d0f2 kept it for the Adopter Admin catalog UI),
but who receives a notification is resolved by the producer now
(ai4i_core.kafka.recipients), before the event is ever published, and
travels with the message as a plain list of emails. See delivery.py.
"""
from __future__ import annotations

from dataclasses import dataclass

from ai4i_core.logging import get_logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


@dataclass(frozen=True)
class Recipient:
    """One resolved-by-the-producer recipient. No ``user_id`` — the
    envelope carries only email addresses (ai4i_core.kafka.recipients
    resolves and decrypts on the producer side), so there is no per-
    recipient identity left to look up here."""

    email: str
    display_name: str


async def fetch_institution_name(db: AsyncSession, *, tenant_id: str) -> str:
    """tenants.organisation — the "[Institution Name]" every email_templates.py
    subject line and body needs (memory: "tenant label value is now
    organisation name, not id" — same field, same reasoning here: it's the
    tenant's actual display identity, not tenants.name, which is an internal
    contact/reference name). Falls back to the bare tenant_id string on a
    miss (deleted tenant, non-numeric id) rather than failing the whole
    send — a slightly ugly subject line beats no email at all."""
    if not tenant_id.isdigit():
        logger.error("fetch_institution_name(): non-numeric tenant_id=%r", tenant_id)
        return tenant_id
    result = await db.execute(
        text("SELECT organisation FROM tenants WHERE id = :tenant_id"),
        {"tenant_id": int(tenant_id)},
    )
    row = result.first()
    if row is None or not row[0]:
        logger.warning("No organisation name for tenant_id=%s — using raw id", tenant_id)
        return tenant_id
    return row[0]
