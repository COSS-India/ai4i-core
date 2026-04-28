"""Single dispatch point for provider selection.

To add a new provider (e.g. SendGrid HTTP API):
1. Add a module under this package implementing EmailProvider.
2. Add an elif branch below.
3. Add provider-specific settings fields to EmailSettings.
No consumer-side code changes are required.
"""

import logging

from ai4icore_email.exceptions import EmailConfigError
from ai4icore_email.providers.base import EmailProvider
from ai4icore_email.providers.console import ConsoleEmailProvider
from ai4icore_email.providers.smtp import SmtpEmailProvider
from ai4icore_email.settings import EmailSettings

logger = logging.getLogger(__name__)


def _common_kwargs(settings: EmailSettings, extra_headers: dict[str, str]) -> dict:
    """Shared constructor kwargs for every provider — sender identity + headers."""
    return {
        "default_from_email": settings.email_from,
        "default_from_name": settings.email_from_name,
        "default_reply_to": settings.email_reply_to,
        "extra_headers": extra_headers,
    }


def build_provider(settings: EmailSettings) -> EmailProvider:
    extra_headers = settings.parsed_extra_headers()
    common = _common_kwargs(settings, extra_headers)
    provider_name = settings.email_provider.strip().lower()

    if provider_name == "console":
        return ConsoleEmailProvider(**common)

    if provider_name == "smtp":
        if not settings.smtp_host:
            if settings.is_dev():
                logger.warning(
                    "EMAIL_PROVIDER=smtp but SMTP_HOST is empty; "
                    "falling back to ConsoleEmailProvider (development env)."
                )
                return ConsoleEmailProvider(**common)
            raise EmailConfigError(
                "SMTP_HOST is required when EMAIL_PROVIDER=smtp in non-development environments"
            )
        if not settings.email_from:
            raise EmailConfigError("EMAIL_FROM is required to send email")
        return SmtpEmailProvider(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
            timeout=settings.smtp_timeout,
            **common,
        )

    raise EmailConfigError(
        f"Unknown EMAIL_PROVIDER='{settings.email_provider}'. "
        "Supported: 'smtp', 'console'."
    )
