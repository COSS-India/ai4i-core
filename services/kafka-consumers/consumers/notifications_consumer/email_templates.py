"""The two email templates every event_name renders through — "notification"
(the general case) or "alert" (the 2 threshold events), same split as the
original design.

No per-event knowledge lives in the field mapping (or anywhere else in this
consumer any more — see delivery.py/emailer.py's own docstrings):
``event_name`` and ``tenant_name`` are opaque strings dropped straight into
the subject line and heading. ``details`` is mapped positionally onto
fixed, ordered field slots — ``details[0]`` -> ``field_1``, ``details[1]``
-> ``field_2``, and so on — the same "first val of details -> first val of
template" contract for every event_name; nothing here checks how many
values a given event_name actually needs or what any of them mean. An
event that uses fewer than _FIELD_COUNT slots just leaves the rest blank in
the notification template (an unfilled field's line is omitted entirely
rather than rendering blank); a producer sending more than _FIELD_COUNT is
a contract change that needs a slot added below, same as it would need a
template change either way.

The one remaining piece of event_name-specific knowledge is _ALERT_EVENTS —
which of the two templates (and which subject format) to use — since an
Alert's subject/heading includes a "%", and the notification template
otherwise doesn't. Picking a template file is not the per-event value
parsing/validation the "blind mapping" rule is about; it's the same
choice a human editing a template by hand would have to make.

Templates live alongside this module under templates/emails/.
"""

from pathlib import Path
from typing import Any, List

from ai4i_core.email import EmailMessage, TemplateRenderer

from consumers.notifications_consumer.config import get_settings

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "emails"
_renderer = TemplateRenderer([_TEMPLATE_DIR])

# How many ordered "field_N" slots each template exposes. Bump this (and add
# the matching field_N reference to the templates) if a future event_name
# needs more positions than this — nothing here enforces any particular
# event_name uses exactly this many.
_FIELD_COUNT = 6

# The only two events that render as an Alert rather than a Notification —
# field_1/field_2/field_3 are threshold/alert_datetime/current_value for
# these (alert.html/.txt), same order the producer always sent them in.
_ALERT_EVENTS = {"QUOTA_THRESHOLD", "BUDGET_THRESHOLD"}


def render_email(
    *, to: str, recipient_name: str, event_name: str, tenant_name: str, details: List[Any],
) -> EmailMessage:
    portal_url = get_settings().PORTAL_URL
    ctx = {
        "recipient_name": recipient_name,
        "event_name": event_name,
        "tenant_name": tenant_name,
        "portal_url": portal_url,
    }
    # Blind positional mapping — details[i] -> field_{i+1}, whatever event_name
    # is and regardless of how many values it actually sent. "" (not None)
    # so a template that references a field unconditionally (alert.html/.txt
    # always does) degrades to blank rather than the literal text "None".
    for i in range(_FIELD_COUNT):
        ctx[f"field_{i + 1}"] = details[i] if i < len(details) else ""

    is_alert = event_name in _ALERT_EVENTS
    template = "alert" if is_alert else "notification"
    subject = (
        f"{event_name} at {ctx['field_1']}% — {tenant_name}" if is_alert
        else f"{event_name} — {tenant_name}"
    )

    html, text = _renderer.render(template, ctx)
    return EmailMessage(to=to, subject=subject, html_body=html, text_body=text)
