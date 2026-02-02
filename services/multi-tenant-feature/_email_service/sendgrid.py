import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from .base import EmailService

from logger import logger
from dotenv import load_dotenv
load_dotenv()

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "no-reply@ai4i.com")

class SendGridEmailService(EmailService):

    async def send(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: str | None = None,
    ):
        message = Mail(
            from_email=FROM_EMAIL,
            to_emails=to_email,
            subject=subject,
            plain_text_content=body,
            html_content=html_body,
        )

        try:
            sg = SendGridAPIClient(SENDGRID_API_KEY)
            response = sg.send(message)
            logger.info(f"SendGrid email sent. Status code: {response.status_code}")
            if response.status_code >= 400:
                logger.debug(f"Response body: {response.body}")
        except Exception as exc:  # noqa: BLE001
            body = getattr(exc, "body", None)
            logger.error(f"Error sending SendGrid test email: {exc}")
            if body:
                logger.error(f"SendGrid error body: {body}")

email_service = SendGridEmailService()
