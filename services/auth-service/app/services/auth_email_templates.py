"""Auth-service email render helpers.

Each function takes domain objects and returns a fully-rendered EmailMessage
that the lib's EmailClient can deliver. Templates live alongside this module
under app/templates/emails/ and are auto-escaped (HTML) by TemplateRenderer.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

from ai4i_core.email import EmailMessage, TemplateRenderer

from app.core.config import settings
from app.core.constants import ENV_DEVELOPMENT
from app.models.user import User

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "emails"
_renderer = TemplateRenderer([_TEMPLATE_DIR])

_DEFAULT_PLATFORM_NAME = "AI Switch"


def _display_name(user: User) -> str:
    """Render-safe greeting name. Falls back to a generic greeting when
    full_name is missing — never the username (per security spec: emails must
    not reveal credentials, and username is part of the credential pair)."""
    return user.full_name or "there"


def _platform_name() -> str:
    """Adopter-configurable product name (EMAIL_FROM_NAME / default AI Switch)."""
    name = (settings.email_from_name or "").strip()
    return name or _DEFAULT_PLATFORM_NAME


def _build_link(base: Optional[str], token: str, *, env_var: str) -> str:
    """HTTPS-only URL builder for email-embedded tokens.

    Allows http://localhost / http://127.0.0.1 only in development. ``env_var``
    is used in error messages so misconfig points at the right setting.
    """
    if not base:
        raise ValueError(f"{env_var} is not configured")
    if not base.startswith("https://"):
        is_dev = settings.environment.strip().lower() == ENV_DEVELOPMENT
        is_localhost = base.startswith(("http://localhost", "http://127.0.0.1"))
        if not (is_dev and is_localhost):
            raise ValueError(
                f"{env_var} must be HTTPS "
                "(http://localhost is allowed only in development)"
            )
    return f"{base}?token={quote_plus(token)}"


def build_setup_url(token: str) -> str:
    return _build_link(settings.setup_link_base_url, token, env_var="SETUP_LINK_BASE_URL")


def build_verify_url(token: str) -> str:
    return _build_link(settings.verify_link_base_url, token, env_var="VERIFY_LINK_BASE_URL")


def build_reset_url(token: str) -> str:
    return _build_link(settings.reset_link_base_url, token, env_var="RESET_LINK_BASE_URL")


def _render(template: str, *, to: str, subject: str, ctx: dict) -> EmailMessage:
    """Render an HTML+text template pair into an EmailMessage."""
    html, text = _renderer.render(
        template,
        {**ctx, "platform_name": _platform_name()},
    )
    return EmailMessage(to=to, subject=subject, html_body=html, text_body=text)


def render_welcome(user: User) -> EmailMessage:
    """Post-activation welcome email. Sent after the user clicks either the
    verify-email link OR the setup-password link, confirming their account is
    now active. Distinct from the verify/setup emails — this has no token.

    Per security spec: no username in any email body. Only display_name
    (which falls back to a generic greeting, never the username) and the
    email address itself (which the recipient already knows)."""
    name = _platform_name()
    return _render(
        "welcome",
        to=user.email,
        subject=f"Welcome to {name}",
        ctx={
            "display_name": _display_name(user),
            "email": user.email,
        },
    )


def render_verify_email(user: User, verify_token: str) -> EmailMessage:
    name = _platform_name()
    return _render(
        "verify_email",
        to=user.email,
        subject=f"Verify your email — {name}",
        ctx={
            "display_name": _display_name(user),
            "verify_url": build_verify_url(verify_token),
            "expires_hours": settings.setup_token_expire_hours,
        },
    )


def render_setup_link(user: User, setup_token: str) -> EmailMessage:
    """Setup-link email — sent on tenant-admin / tenant-user activation.

    Per product spec (reference UI: 'Welcome to AI4I!'): no greeting, no
    username; the recipient sees an account-was-created message and a
    Set Your Password CTA. Single-use, 48-hour expiry."""
    name = _platform_name()
    return _render(
        "setup_link",
        to=user.email,
        subject=f"Welcome to {name} — Set Your Password",
        ctx={
            "setup_url": build_setup_url(setup_token),
            "expires_hours": settings.setup_token_expire_hours,
        },
    )


def render_password_reset(user: User, reset_token: str) -> EmailMessage:
    """Password-reset email triggered by /auth/forgot-password. Short 30-min
    expiry per security spec — much tighter than setup/verify. Content
    aligned to product spec: no greeting, no username, terse copy."""
    name = _platform_name()
    return _render(
        "password_reset",
        to=user.email,
        subject=f"Reset Your Password — {name}",
        ctx={
            "reset_url": build_reset_url(reset_token),
            "expires_minutes": settings.reset_token_expire_minutes,
        },
    )


def render_password_changed(user: User, when: Optional[datetime] = None) -> EmailMessage:
    when = when or datetime.now(timezone.utc)
    name = _platform_name()
    return _render(
        "password_changed",
        to=user.email,
        subject=f"Your {name} password was changed",
        ctx={
            "display_name": _display_name(user),
            "when": when.strftime("%Y-%m-%d %H:%M:%S"),
        },
    )


def render_quota_limit_updated(user: User, tier_name: str) -> EmailMessage:
    name = _platform_name()
    return _render(
        "quota_limit_updated",
        to=user.email,
        subject=f"Tier quota limit updated — {name}",
        ctx={
            "display_name": _display_name(user),
            "tier_name": tier_name,
        },
    )


def render_account_deleted(email: str, full_name: Optional[str] = None) -> EmailMessage:
    """Deletion confirmation sent to the user's original address.

    ``email`` and ``full_name`` must be captured before the account is
    anonymised and passed explicitly so this function is safe to call after
    the DB commit that overwrites those fields.
    """
    name = _platform_name()
    return _render(
        "account_deleted",
        to=email,
        subject=f"Your {name} account has been deleted",
        ctx={
            "display_name": full_name or "there",
        },
    )
