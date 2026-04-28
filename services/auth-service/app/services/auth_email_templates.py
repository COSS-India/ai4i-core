"""Auth-service email render helpers.

Each function takes domain objects and returns a fully-rendered EmailMessage
that the lib's EmailClient can deliver. Templates live alongside this module
under app/templates/emails/ and are auto-escaped (HTML) by TemplateRenderer.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

from ai4icore_email import EmailMessage, TemplateRenderer

from app.core.config import settings
from app.models.user import User

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "emails"
_renderer = TemplateRenderer([_TEMPLATE_DIR])


def _display_name(user: User) -> str:
    return user.full_name or user.username or user.email


def build_setup_url(token: str) -> str:
    base = settings.setup_link_base_url
    if not base:
        raise ValueError("SETUP_LINK_BASE_URL is not configured")
    if not base.startswith("https://"):
        # Permit http://localhost* and http://127.0.0.1* in development only.
        is_dev = settings.environment.strip().lower() == "development"
        is_localhost = base.startswith(("http://localhost", "http://127.0.0.1"))
        if not (is_dev and is_localhost):
            raise ValueError(
                "SETUP_LINK_BASE_URL must be HTTPS "
                "(http://localhost is allowed only in development)"
            )
    return f"{base}?token={quote_plus(token)}"


def _render(template: str, *, to: str, subject: str, ctx: dict) -> EmailMessage:
    """Render an HTML+text template pair into an EmailMessage."""
    html, text = _renderer.render(template, ctx)
    return EmailMessage(to=to, subject=subject, html_body=html, text_body=text)


def render_welcome(user: User) -> EmailMessage:
    return _render(
        "welcome",
        to=user.email,
        subject="Welcome to AI4I Platform",
        ctx={
            "display_name": _display_name(user),
            "username": user.username,
            "email": user.email,
        },
    )


def render_setup_link(user: User, setup_token: str) -> EmailMessage:
    return _render(
        "setup_link",
        to=user.email,
        subject="Activate your AI4I Platform account",
        ctx={
            "display_name": _display_name(user),
            "setup_url": build_setup_url(setup_token),
            "expires_hours": settings.setup_token_expire_hours,
        },
    )


def render_password_changed(user: User, when: Optional[datetime] = None) -> EmailMessage:
    when = when or datetime.now(timezone.utc)
    return _render(
        "password_changed",
        to=user.email,
        subject="Your AI4I Platform password was changed",
        ctx={
            "display_name": _display_name(user),
            "when": when.strftime("%Y-%m-%d %H:%M:%S"),
        },
    )
