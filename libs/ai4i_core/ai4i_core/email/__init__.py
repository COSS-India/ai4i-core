from ai4i_core.email.client import EmailClient
from ai4i_core.email.exceptions import EmailConfigError, EmailDeliveryError
from ai4i_core.email.fastapi import get_email_client
from ai4i_core.email.message import EmailMessage
from ai4i_core.email.providers.base import EmailProvider
from ai4i_core.email.settings import EmailSettings
from ai4i_core.email.templates import TemplateRenderer

__all__ = [
    "EmailClient",
    "EmailConfigError",
    "EmailDeliveryError",
    "EmailMessage",
    "EmailProvider",
    "EmailSettings",
    "TemplateRenderer",
    "get_email_client",
]
