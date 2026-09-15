"""Sends the email directly — no auth-service call. Wraps ai4i_core.email
the same way auth-service's own auth_email_templates.py does: one shared
EmailClient, and rendering delegated to email_templates.py (the branded
Reference Email Template set ported from platform-core-service, PR #1557 —
see that module's own docstring).

The client is built once per process (module-level), not per message —
EmailSettings reads the environment once.

``details`` is a plain, positional array now, not a dict — design doc §9.
The producer supplies one already-final, display-ready value per template
placeholder, in the exact order that event_name's row in §9's table
specifies; nothing here parses dates, computes a percentage, or formats a
"X of Y" string any more — that used to happen here (occurred_at ->
alert_datetime, previous/current -> "changed from X to Y", etc.), and moved
to the producer side specifically so this consumer never has to guess at
formatting again. _build_message below does nothing but pick the right
email_templates.py renderer for event_name and plug each position straight
into its matching keyword argument, in order.

institution_name and recipient_name are NOT part of ``details`` — the
consumer resolves both itself (recipients.py: tenants.organisation for the
former, per-recipient full_name for the latter) since it already has
everything it needs to do that without round-tripping through the producer.
"""
from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any, List

from ai4i_core.email import EmailClient, EmailMessage
from ai4i_core.email.providers.factory import build_provider
from ai4i_core.email.settings import EmailSettings
from ai4i_core.logging import get_logger

from consumers.notifications_consumer import email_templates
from consumers.notifications_consumer.recipients import Recipient

logger = get_logger(__name__)

# Belt-and-braces on top of EmailSettings.smtp_timeout (which aiosmtplib.send
# is given directly): a hung DNS lookup or a silently-dropped TCP connect
# (a firewall dropping outbound SMTP with no RST, common on WSL/corporate
# networks) isn't guaranteed to be covered by the provider's own timeout, and
# this consumer's loop is fully sequential — one stuck send blocks every
# other Kafka message behind it, and eventually costs the group its
# partition (KAFKA_MAX_POLL_INTERVAL_MS). A hard deadline here means a
# send that can't complete becomes "failed", not "wedged forever".
_SEND_DEADLINE_S = 20.0

_MISSING = "—"


@lru_cache(maxsize=1)
def _client() -> EmailClient:
    settings = EmailSettings()
    return EmailClient(build_provider(settings))


def _at(details: List[Any], index: int, event_name: str, default: Any = _MISSING) -> Any:
    """details[index], or `default` if the producer sent a short array (a
    trailing optional value it chose not to fill) — degrade to a visibly
    blank placeholder rather than raising IndexError and losing the whole
    send over one missing value.

    Logs a warning naming event_name, the missing index, and how many
    positions the producer actually sent — a short array is either a
    genuine producer/consumer contract mismatch (design doc §9.5 changed on
    one side and not the other) or an intentionally-omitted trailing
    optional value (e.g. TIER_ASSIGNED's rate limit/effective dates, which
    have no data source yet); either way it should show up in logs instead
    of only as a silent "—" in the delivered email."""
    if index < len(details):
        return details[index]
    logger.warning(
        "details[%d] missing for event_name=%s — producer sent %d value(s); "
        "rendering %r for this field",
        index, event_name, len(details), default,
    )
    return default


def _build_message(
    *, recipient: Recipient, institution_name: str, event_name: str, details: List[Any],
) -> EmailMessage:
    """Design doc §9's per-event_name table gives the exact position ->
    meaning mapping this dispatch mirrors — keep the two in sync."""
    common = dict(to=recipient.email, recipient_name=recipient.display_name, institution_name=institution_name)

    if event_name == "TIER_ASSIGNED":
        return email_templates.render_tier_assigned_email(
            **common,
            tier_name=_at(details, 0, event_name),
            tier_description=_at(details, 1, event_name),
            quota_lines=_at(details, 2, event_name, default=[]),
            rate_limit_value=_at(details, 3, event_name),
            effective_from=_at(details, 4, event_name),
            effective_to=_at(details, 5, event_name),
        )
    if event_name == "TIER_CHANGED":
        return email_templates.render_tier_reassigned_email(
            **common,
            current_tier_name=_at(details, 0, event_name),
            new_tier_name=_at(details, 1, event_name),
            new_tier_description=_at(details, 2, event_name),
            quota_lines=_at(details, 3, event_name, default=[]),
            new_rate_limit_value=_at(details, 4, event_name),
            effective_from=_at(details, 5, event_name),
            effective_to=_at(details, 6, event_name),
        )
    if event_name == "BUDGET_ASSIGNED":
        return email_templates.render_budget_assigned_email(
            **common, currency=_at(details, 0, event_name), budget_amount=_at(details, 1, event_name),
        )
    if event_name == "BUDGET_UPDATED":
        return email_templates.render_budget_revised_email(
            **common,
            currency=_at(details, 0, event_name),
            previous_value=_at(details, 1, event_name),
            new_value=_at(details, 2, event_name),
            effective_date=_at(details, 3, event_name),
        )
    if event_name == "QUOTA_LIMIT_UPDATED":
        return email_templates.render_quota_limit_updated_email(
            **common,
            tier_name=_at(details, 0, event_name),
            changes=_at(details, 1, event_name, default=[]),
            effective_date=_at(details, 2, event_name),
        )
    if event_name == "QUOTA_EXHAUSTED":
        return email_templates.render_quota_exhausted_email(
            **common,
            tier_name=_at(details, 0, event_name),
            exhausted_lines=_at(details, 1, event_name, default=[]),
        )
    if event_name == "BUDGET_EXHAUSTED":
        return email_templates.render_budget_exhausted_email(
            **common, currency=_at(details, 0, event_name), budget_amount=_at(details, 1, event_name),
        )
    if event_name == "QUOTA_THRESHOLD":
        return email_templates.render_quota_threshold_alert_email(
            **common,
            threshold=_at(details, 0, event_name),
            alert_datetime=_at(details, 1, event_name),
            current_value=_at(details, 2, event_name),
        )
    if event_name == "BUDGET_THRESHOLD":
        return email_templates.render_budget_threshold_alert_email(
            **common,
            threshold=_at(details, 0, event_name),
            alert_datetime=_at(details, 1, event_name),
            current_value=_at(details, 2, event_name),
        )
    raise ValueError(f"No email template mapping for event_name={event_name!r}")


async def send_one(
    *, recipient: Recipient, institution_name: str, event_name: str, details: List[Any],
) -> bool:
    """True on a confirmed send. Never raises and never blocks past
    _SEND_DEADLINE_S — provider failures are logged and reported as False
    (EmailClient.send_safe), and a hang past the deadline is treated the
    same way, so one bad or unreachable recipient can't take the others
    (or the whole consumer) down with it."""
    try:
        message = _build_message(
            recipient=recipient, institution_name=institution_name, event_name=event_name, details=details,
        )
        return await asyncio.wait_for(_client().send_safe(message), timeout=_SEND_DEADLINE_S)
    except asyncio.TimeoutError:
        logger.error(
            "Email send timed out after %.0fs — treating as failed | to=%s event_name=%s",
            _SEND_DEADLINE_S, recipient.email, event_name,
        )
        return False
    except Exception:
        # _build_message lives inside this try too (an unmapped event_name,
        # or a StrictUndefined miss on a key its template expects) — this
        # function's contract is "never raises", so any failure here is
        # reported as False, not propagated. delivery.py's
        # gather(return_exceptions=True) is a second, independent guard
        # against this same class of bug, not a substitute for it.
        logger.exception(
            "send_one failed before/during send | to=%s event_name=%s",
            recipient.email, event_name,
        )
        return False
