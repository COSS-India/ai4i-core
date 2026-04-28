"""Provider abstraction.

A provider is anything that can deliver a fully-rendered EmailMessage.
Concrete providers in this package: SmtpEmailProvider, ConsoleEmailProvider.
Future providers (SendGrid HTTP, Mailgun HTTP, boto3 SES, etc.) implement
the same Protocol and register in providers/factory.py — no consumer code
changes.
"""

from typing import Protocol, runtime_checkable

from ai4icore_core.email.message import EmailMessage


@runtime_checkable
class EmailProvider(Protocol):
    name: str

    async def send(self, message: EmailMessage) -> None:
        """Deliver the message. Raise EmailDeliveryError on failure."""
        ...
