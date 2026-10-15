"""Usage Viewer report email: render, attach the PDF, send (AI4IDS-3278).

ai4i_core's EmailMessage/EmailClient have no attachment support, and the
library ships from PyPI, so the MIME is built here: ai4i_core's own
build_mime (same headers and CR/LF guards as every other email) with the PDF
added, then sent with the same SMTP settings SmtpEmailProvider uses.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from pathlib import Path
from typing import Awaitable, Callable, Optional

import aiosmtplib
from ai4i_core.email import EmailDeliveryError, EmailMessage, EmailSettings, TemplateRenderer
from ai4i_core.email.message import build_mime

from app.core.config import settings
from app.services.usage_report import formatting as fmt
from app.services.usage_report.collector import ReportData

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates" / "emails"
_renderer = TemplateRenderer([_TEMPLATE_DIR])

# Brand, title, team and file name come from settings (USAGE_REPORT_*,
# falling back to PLATFORM_NAME); only the portal route is fixed here.
DASHBOARD_PATH = "/usage-dashboard"


def attachment_name(data: ReportData) -> str:
    return f"{settings.get_usage_report_filename_prefix()}_{data.period.key}.pdf"


def subject(data: ReportData) -> str:
    return f"{settings.get_usage_report_subject_prefix()} – {data.period.title} programme report – {data.period.label}"


def portal_link() -> Optional[str]:
    return f"{settings.portal_url.rstrip('/')}{DASHBOARD_PATH}" if settings.portal_url else None


def summary_lines(data: ReportData) -> list[str]:
    """Only figures the platform tracks. Availability, P95 latency, providers,
    financial-year totals and the budget line are left out until they are;
    platform health (error rate) is not part of the report."""
    live_change = (
        f" ({fmt.signed_int(data.active_institutions_change)} {data.period.vs_phrase})"
        if data.active_institutions_change is not None else ""
    )
    requests_change = (
        f" ({fmt.signed_pct(data.requests_change_pct)})" if data.requests_change_pct is not None else ""
    )
    return [
        f"Model portfolio: {fmt.count(data.total_models)} Models; "
        f"{fmt.count(data.active_models)} were used {data.period.in_phrase}.",
        f"Adoption: {fmt.count(data.active_institutions)} of {fmt.count(data.total_institutions)} "
        f"Institutions were live{live_change}. {fmt.count(data.total_requests)} requests were "
        f"served{requests_change}.",
    ]


@dataclass(frozen=True)
class RenderedEmail:
    """The email's content — the same for every recipient."""
    subject: str
    html: str
    text: str


def render_content(data: ReportData) -> RenderedEmail:
    subj = subject(data)
    html, text = _renderer.render(
        "usage_report",
        {
            "subject": subj,
            "report_name": settings.get_usage_report_title(),
            "period_label": data.period.label,
            "summary": summary_lines(data),
            "attachment_name": attachment_name(data),
            "portal_link": portal_link(),
            "sender_name": settings.usage_report_sender_name,
            "team_name": settings.get_usage_report_team_name(),
            "platform_name": settings.get_platform_name(),
            "logo_url": settings.get_adopter_logo_url(),
        },
    )
    return RenderedEmail(subj, html, text)


def render_email(data: ReportData, to: str, content: Optional[RenderedEmail] = None) -> EmailMessage:
    """The email for one recipient; pass ``content`` to reuse one rendering."""
    c = content or render_content(data)
    return EmailMessage(to=to, subject=c.subject, html_body=c.html, text_body=c.text)


def email_settings() -> EmailSettings:
    """Same EmailSettings platform-core's EmailClient is built from
    (app.dependencies.services._email_client_singleton)."""
    s = EmailSettings()
    return s.model_copy(update={"email_from_name": settings.resolve_smtp_from_name(s.email_from_name)})


def build_report_mime(
    message: EmailMessage, pdf: bytes, filename: str, email_cfg: EmailSettings
) -> MimeMessage:
    mime = build_mime(
        message,
        default_from_email=email_cfg.email_from,
        default_from_name=email_cfg.email_from_name,
        default_reply_to=email_cfg.email_reply_to,
        extra_headers=email_cfg.parsed_extra_headers(),
    )
    # Turns the multipart/alternative body into multipart/mixed with the PDF.
    mime.add_attachment(pdf, maintype="application", subtype="pdf", filename=filename)
    return mime


async def send_report_mime(mime: MimeMessage, email_cfg: EmailSettings) -> None:
    """Send over SMTP exactly as SmtpEmailProvider does. Raises
    EmailDeliveryError on failure, or when SMTP is not configured — unlike
    the library's console fallback, a report run must not report success
    for an email nobody received."""
    if not email_cfg.smtp_host or email_cfg.email_provider.strip().lower() != "smtp":
        raise EmailDeliveryError(
            "SMTP is not configured (EMAIL_PROVIDER=smtp and SMTP_HOST are required to send the report)"
        )
    if not email_cfg.email_from:
        raise EmailDeliveryError("EMAIL_FROM is required to send the report")
    try:
        await aiosmtplib.send(
            mime,
            hostname=email_cfg.smtp_host,
            port=email_cfg.smtp_port,
            username=email_cfg.smtp_username,
            password=email_cfg.smtp_password,
            start_tls=email_cfg.smtp_use_tls,
            validate_certs=True,
            timeout=email_cfg.smtp_timeout,
        )
    except (aiosmtplib.SMTPException, OSError) as exc:
        raise EmailDeliveryError(
            f"SMTP send failed via {email_cfg.smtp_host}:{email_cfg.smtp_port}"
        ) from exc


Sender = Callable[[MimeMessage, EmailSettings], Awaitable[None]]


async def deliver(
    data: ReportData,
    pdf: bytes,
    recipients: list[str],
    email_cfg: EmailSettings,
    send: Sender = send_report_mime,
    on_result: Optional[Callable[[str, Optional[str]], None]] = None,
) -> tuple[list[str], dict[str, str]]:
    """One email per recipient, so no recipient sees another's address. A
    failed recipient is logged and the rest still get theirs. ``on_result``
    is called right after each attempt with (recipient, error or None), so a
    caller's record of who got it survives a crash part-way through.

    Returns (sent recipients, {failed recipient: error})."""
    filename = attachment_name(data)
    content = render_content(data)  # once: the template doesn't vary by recipient
    sent: list[str] = []
    failed: dict[str, str] = {}
    for to in recipients:
        try:
            await send(build_report_mime(render_email(data, to, content), pdf, filename, email_cfg), email_cfg)
            sent.append(to)
        except Exception as exc:
            reason = exc.__cause__.__class__.__name__ if exc.__cause__ else exc.__class__.__name__
            failed[to] = f"{exc} ({reason})"
            logger.error("usage report %s NOT sent to %s: %s", data.period.key, to, failed[to])
        if on_result is not None:
            on_result(to, failed.get(to))
    return sent, failed
