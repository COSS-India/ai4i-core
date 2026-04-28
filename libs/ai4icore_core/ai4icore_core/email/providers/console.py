"""Dev-only provider that logs the rendered message instead of sending.

Auto-selected by the factory when EMAIL_PROVIDER=smtp + SMTP_HOST is empty
+ ENVIRONMENT=development. Never used in staging/production — the factory
raises EmailConfigError there.
"""

import logging
from typing import Optional

from ai4icore_core.email.message import EmailMessage, build_mime

logger = logging.getLogger(__name__)


class ConsoleEmailProvider:
    name = "console"

    def __init__(
        self,
        *,
        default_from_email: Optional[str],
        default_from_name: str,
        default_reply_to: Optional[str],
        extra_headers: dict[str, str],
    ) -> None:
        self._default_from_email = default_from_email or "dev@localhost"
        self._default_from_name = default_from_name
        self._default_reply_to = default_reply_to
        self._extra_headers = extra_headers

    async def send(self, message: EmailMessage) -> None:
        mime = build_mime(
            message,
            default_from_email=self._default_from_email,
            default_from_name=self._default_from_name,
            default_reply_to=self._default_reply_to,
            extra_headers=self._extra_headers,
        )
        logger.info(
            "[ConsoleEmailProvider] would send email\n"
            "  From:    %s\n"
            "  To:      %s\n"
            "  Subject: %s\n"
            "  Text body:\n%s",
            mime["From"],
            mime["To"],
            mime["Subject"],
            message.text_body,
        )
