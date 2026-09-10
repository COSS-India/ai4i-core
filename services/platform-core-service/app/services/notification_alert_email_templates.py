"""Notification / Alert email templates.

Fixed, backend-only templates — not editable from the Portal. Callers (the
notification and alert trigger code) supply already-formatted display
strings; this module only renders and wraps them into an EmailMessage. Send
it with ``app.services.email_helpers.enqueue_email`` (or ``EmailClient.send``
/ ``send_safe`` directly) — this module never sends mail itself.

Two kinds of template live here:

- The generic **Standard** Notification/Alert templates (``render_notification_
  email`` / ``render_alert_email``) — the fallback shape for any event that
  doesn't have a dedicated template of its own.
- **Dedicated** templates for specific Configuration Update / Proactive
  Governance events (Tier Assigned, Budget Exhausted, Quota Threshold Alert,
  etc.) — each with its own fixed subject/body copy that does NOT follow the
  Standard shape, per their own PRD spec. These take precedence over the
  generic ones for their specific event.

Templates live alongside this module under app/templates/emails/.
"""

from pathlib import Path
from typing import List

from ai4i_core.email import EmailMessage, TemplateRenderer

from app.core.config import settings

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "emails"
_renderer = TemplateRenderer([_TEMPLATE_DIR])


def _render(template: str, *, to: str, subject: str, ctx: dict) -> EmailMessage:
    html, text = _renderer.render(template, {**ctx, "portal_url": settings.portal_url})
    return EmailMessage(to=to, subject=subject, html_body=html, text_body=text)


def render_notification_email(
    *,
    to: str,
    recipient_name: str,
    notification_name: str,
    institution_name: str,
    effective_date: str,
    notification_details: str,
) -> EmailMessage:
    """Standard Notification Email Template.

    All fields are pre-formatted display strings — the caller (notification
    trigger code) owns formatting (e.g. dates, amounts, "Tier changed from X
    to Y" phrasing); this function only fills the fixed template shape.
    """
    return _render(
        "notification",
        to=to,
        subject=f"{notification_name} — {institution_name}",
        ctx={
            "recipient_name": recipient_name,
            "notification_name": notification_name,
            "institution_name": institution_name,
            "effective_date": effective_date,
            "notification_details": notification_details,
        },
    )


def render_alert_email(
    *,
    to: str,
    recipient_name: str,
    alert_name: str,
    institution_name: str,
    effective_date: str,
    threshold: str,
    current_value: str,
) -> EmailMessage:
    """Standard Alert Email Template.

    ``threshold`` and ``current_value`` are pre-formatted display strings
    (e.g. "80", "92.4") — the caller owns numeric formatting.
    """
    return _render(
        "alert",
        to=to,
        subject=f"{alert_name} at {threshold}% — {institution_name}",
        ctx={
            "recipient_name": recipient_name,
            "alert_name": alert_name,
            "institution_name": institution_name,
            "effective_date": effective_date,
            "threshold": threshold,
            "current_value": current_value,
        },
    )


# ── Configuration Update Notifications (dedicated templates — do not follow
# the Standard Notification shape; see module docstring) ──


def render_tier_assigned_email(
    *,
    to: str,
    recipient_name: str,
    tier_name: str,
    effective_date: str,
    tier_description: str,
    quota_lines: List[str],
    rate_limit_value: str,
) -> EmailMessage:
    """``quota_lines`` are pre-formatted "Task Type: Quota Limit" strings, one per line."""
    return _render(
        "tier_assigned",
        to=to,
        subject=f"Your Tier has been assigned — {tier_name}",
        ctx={
            "recipient_name": recipient_name,
            "tier_name": tier_name,
            "effective_date": effective_date,
            "tier_description": tier_description,
            "quota_lines": quota_lines,
            "rate_limit_value": rate_limit_value,
        },
    )


def render_budget_assigned_email(
    *,
    to: str,
    recipient_name: str,
    currency: str,
    budget_amount: str,
) -> EmailMessage:
    return _render(
        "budget_assigned",
        to=to,
        subject=f"Your Budget has been set — {currency} {budget_amount}",
        ctx={
            "recipient_name": recipient_name,
            "currency": currency,
            "budget_amount": budget_amount,
        },
    )


def render_tier_reassigned_email(
    *,
    to: str,
    recipient_name: str,
    current_tier_name: str,
    new_tier_name: str,
    effective_date: str,
) -> EmailMessage:
    return _render(
        "tier_reassigned",
        to=to,
        subject=f"Tier change scheduled — {current_tier_name} to {new_tier_name}",
        ctx={
            "recipient_name": recipient_name,
            "current_tier_name": current_tier_name,
            "new_tier_name": new_tier_name,
            "effective_date": effective_date,
        },
    )


def render_tier_deactivated_email(
    *,
    to: str,
    recipient_name: str,
    tier_name: str,
    effective_date: str,
) -> EmailMessage:
    """No portal-login CTA — access is suspended, per spec."""
    return _render(
        "tier_deactivated",
        to=to,
        subject="Your Tier has been deactivated",
        ctx={
            "recipient_name": recipient_name,
            "tier_name": tier_name,
            "effective_date": effective_date,
        },
    )


def render_tier_reactivated_email(
    *,
    to: str,
    recipient_name: str,
    tier_name: str,
    effective_date: str,
) -> EmailMessage:
    return _render(
        "tier_reactivated",
        to=to,
        subject="Your Tier has been reactivated",
        ctx={
            "recipient_name": recipient_name,
            "tier_name": tier_name,
            "effective_date": effective_date,
        },
    )


def render_quota_limit_updated_email(
    *,
    to: str,
    recipient_name: str,
    model_task_type: str,
    tier_name: str,
    current_value: str,
    new_value: str,
    effective_date: str,
) -> EmailMessage:
    return _render(
        "quota_limit_updated",
        to=to,
        subject=f"Quota Limit updated — {model_task_type}",
        ctx={
            "recipient_name": recipient_name,
            "model_task_type": model_task_type,
            "tier_name": tier_name,
            "current_value": current_value,
            "new_value": new_value,
            "effective_date": effective_date,
        },
    )


def render_rate_limit_updated_email(
    *,
    to: str,
    recipient_name: str,
    tier_name: str,
    current_value: str,
    new_value: str,
    effective_date: str,
) -> EmailMessage:
    return _render(
        "rate_limit_updated",
        to=to,
        subject="Rate Limit updated",
        ctx={
            "recipient_name": recipient_name,
            "tier_name": tier_name,
            "current_value": current_value,
            "new_value": new_value,
            "effective_date": effective_date,
        },
    )


def render_budget_revised_email(
    *,
    to: str,
    recipient_name: str,
    currency: str,
    previous_value: str,
    new_value: str,
    effective_date: str,
) -> EmailMessage:
    return _render(
        "budget_revised",
        to=to,
        subject="Your Budget has been revised",
        ctx={
            "recipient_name": recipient_name,
            "currency": currency,
            "previous_value": previous_value,
            "new_value": new_value,
            "effective_date": effective_date,
        },
    )


def render_quota_exhausted_email(
    *,
    to: str,
    recipient_name: str,
    model_task_type: str,
    quota_limit_value: str,
    billing_period_reset_date: str,
) -> EmailMessage:
    return _render(
        "quota_exhausted",
        to=to,
        subject=f"Quota exhausted — {model_task_type} requests blocked",
        ctx={
            "recipient_name": recipient_name,
            "model_task_type": model_task_type,
            "quota_limit_value": quota_limit_value,
            "billing_period_reset_date": billing_period_reset_date,
        },
    )


def render_budget_exhausted_email(
    *,
    to: str,
    recipient_name: str,
    currency: str,
    budget_amount: str,
) -> EmailMessage:
    """No portal-login CTA — requests are blocked, per spec."""
    return _render(
        "budget_exhausted",
        to=to,
        subject="Budget exhausted — requests blocked",
        ctx={
            "recipient_name": recipient_name,
            "currency": currency,
            "budget_amount": budget_amount,
        },
    )


# ── PPU-15: Proactive Governance Notifications (dedicated alert templates) ──


def render_quota_threshold_alert_email(
    *,
    to: str,
    recipient_name: str,
    model_task_type: str,
    tier_name: str,
    threshold: str,
    consumed: str,
    remaining: str,
    reset_date: str,
) -> EmailMessage:
    """Tenant-admin-facing quota threshold alert."""
    return _render(
        "quota_threshold_alert",
        to=to,
        subject=f"Quota alert — {model_task_type} at {threshold}% of limit",
        ctx={
            "recipient_name": recipient_name,
            "model_task_type": model_task_type,
            "tier_name": tier_name,
            "threshold": threshold,
            "consumed": consumed,
            "remaining": remaining,
            "reset_date": reset_date,
        },
    )


def render_budget_threshold_alert_email(
    *,
    to: str,
    recipient_name: str,
    threshold: str,
    currency: str,
    cumulative_spend: str,
    remaining_budget: str,
) -> EmailMessage:
    """Tenant-admin-facing budget threshold alert."""
    return _render(
        "budget_threshold_alert",
        to=to,
        subject=f"Budget alert — {threshold}% of Budget reached",
        ctx={
            "recipient_name": recipient_name,
            "threshold": threshold,
            "currency": currency,
            "cumulative_spend": cumulative_spend,
            "remaining_budget": remaining_budget,
        },
    )


def render_quota_threshold_alert_adopter_admin_email(
    *,
    to: str,
    recipient_name: str,
    tenant_name: str,
    model_task_type: str,
    tier_name: str,
    threshold: str,
    consumed: str,
    remaining: str,
    reset_date: str,
) -> EmailMessage:
    """Adopter-admin-facing variant of the quota threshold alert — scoped to one tenant."""
    return _render(
        "quota_threshold_alert_adopter_admin",
        to=to,
        subject=f"Tenant Quota alert — {tenant_name} / {model_task_type} at {threshold}%",
        ctx={
            "recipient_name": recipient_name,
            "tenant_name": tenant_name,
            "model_task_type": model_task_type,
            "tier_name": tier_name,
            "threshold": threshold,
            "consumed": consumed,
            "remaining": remaining,
            "reset_date": reset_date,
        },
    )


def render_budget_threshold_alert_adopter_admin_email(
    *,
    to: str,
    recipient_name: str,
    tenant_name: str,
    threshold: str,
    currency: str,
    cumulative_spend: str,
    remaining_budget: str,
) -> EmailMessage:
    """Adopter-admin-facing variant of the budget threshold alert — scoped to one tenant."""
    return _render(
        "budget_threshold_alert_adopter_admin",
        to=to,
        subject=f"Tenant Budget alert — {tenant_name} at {threshold}%",
        ctx={
            "recipient_name": recipient_name,
            "tenant_name": tenant_name,
            "threshold": threshold,
            "currency": currency,
            "cumulative_spend": cumulative_spend,
            "remaining_budget": remaining_budget,
        },
    )
