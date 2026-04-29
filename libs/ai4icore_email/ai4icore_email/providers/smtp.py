"""Generic SMTP provider.

Works against any RFC-compliant SMTP relay:
- Amazon SES: SMTP_HOST=email-smtp.<region>.amazonaws.com
- SendGrid:   SMTP_HOST=smtp.sendgrid.net, SMTP_USERNAME=apikey
- Mailgun:    SMTP_HOST=smtp.mailgun.org
- Postmark:   SMTP_HOST=smtp.postmarkapp.com
- Internal MTA: SMTP_HOST=<your-host>
"""

import logging
from typing import Optional

import aiosmtplib

from ai4icore_email.exceptions import EmailDeliveryError
from ai4icore_email.message import EmailMessage, build_mime

logger = logging.getLogger(__name__)


class SmtpEmailProvider:
    name = "smtp"

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: Optional[str],
        password: Optional[str],
        use_tls: bool,
        default_from_email: Optional[str],
        default_from_name: str,
        default_reply_to: Optional[str],
        extra_headers: dict[str, str],
        timeout: int = 30,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._default_from_email = default_from_email
        self._default_from_name = default_from_name
        self._default_reply_to = default_reply_to
        self._extra_headers = extra_headers
        self._timeout = timeout

    async def send(self, message: EmailMessage) -> None:
        mime = build_mime(
            message,
            default_from_email=self._default_from_email,
            default_from_name=self._default_from_name,
            default_reply_to=self._default_reply_to,
            extra_headers=self._extra_headers,
        )
        try:
            await aiosmtplib.send(
                mime,
                hostname=self._host,
                port=self._port,
                username=self._username,
                password=self._password,
                start_tls=self._use_tls,
                validate_certs=True,
                timeout=self._timeout,
            )
        except (aiosmtplib.SMTPException, OSError) as exc:
            raise EmailDeliveryError(
                f"SMTP send failed via {self._host}:{self._port}"
            ) from exc
