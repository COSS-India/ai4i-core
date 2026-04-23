from email.message import EmailMessage

import aiosmtplib

from .base import EmailService
from ai4icore_env import app_env
from logger import logger


SMTP_HOST = app_env.smtp_host
SMTP_PORT = app_env.smtp_port
SMTP_USERNAME = app_env.smtp_username
SMTP_PASSWORD = app_env.smtp_password
SMTP_TLS = app_env.smtp_tls
SMTP_FROM_NOREPLY = app_env.smtp_from_noreply or "noreply@ai4inclusion.org"
SMTP_REPLY_TO = app_env.smtp_reply_to or "support@ai4inclusion.org"
RUNTIME_ENV = (app_env.runtime_env or app_env.env or app_env.environment or "").strip().lower()

SES_CONFIGURATION_SET_BY_ENV = {
    "local": "ses-config-dev",
    "dev": "ses-config-dev",
    "development": "ses-config-dev",
    "staging": "ses-config-staging",
    "sandbox": "ses-config-sandbox",
}

SES_CONFIGURATION_SET = SES_CONFIGURATION_SET_BY_ENV.get(RUNTIME_ENV, "ses-config-dev")


class AmazonSESEmailService(EmailService):
    async def send(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: str | None = None,
    ):
        message = EmailMessage()
        message["From"] = SMTP_FROM_NOREPLY
        message["To"] = to_email
        message["Subject"] = subject
        message["Reply-To"] = SMTP_REPLY_TO
        message["X-SES-CONFIGURATION-SET"] = SES_CONFIGURATION_SET
        message.set_content(body)

        if html_body:
            message.add_alternative(html_body, subtype="html")

        try:
            await aiosmtplib.send(
                message,
                hostname=SMTP_HOST,
                port=SMTP_PORT,
                username=SMTP_USERNAME,
                password=SMTP_PASSWORD,
                start_tls=SMTP_TLS,
            )
            logger.info("Amazon SES SMTP email sent successfully")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Error sending Amazon SES SMTP email: {exc}")


email_service = AmazonSESEmailService()
