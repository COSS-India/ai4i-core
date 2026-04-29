"""Provider-agnostic email client.

Holds an EmailProvider and exposes:
- send: raises EmailDeliveryError on provider failure
- send_safe: never raises; logs failure and returns False. Designed to be
  enqueued as a FastAPI BackgroundTask so a flaky provider does not 5xx
  the request.
"""

import logging

from ai4icore_email.exceptions import EmailDeliveryError
from ai4icore_email.message import EmailMessage
from ai4icore_email.providers.base import EmailProvider

logger = logging.getLogger(__name__)


class EmailClient:
    def __init__(self, provider: EmailProvider) -> None:
        self._provider = provider

    @property
    def provider_name(self) -> str:
        return getattr(self._provider, "name", "unknown")

    async def send(self, message: EmailMessage) -> None:
        await self._provider.send(message)

    async def send_safe(self, message: EmailMessage) -> bool:
        try:
            await self._provider.send(message)
            return True
        except Exception as exc:
            # Prefer the underlying cause's type name when the provider wraps
            # (EmailDeliveryError(...) from underlying SMTPException) — gives
            # ops the actual root cause without the abstraction noise.
            unexpected = not isinstance(exc, EmailDeliveryError)
            reason = (
                exc.__cause__.__class__.__name__
                if exc.__cause__
                else exc.__class__.__name__
            )
            logger.error(
                "email send failed%s: provider=%s to=%s subject=%s reason=%s",
                " (unexpected)" if unexpected else "",
                self.provider_name,
                message.to,
                message.subject,
                reason,
            )
            return False
