from fastapi import BackgroundTasks
from datetime import timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from utils.utils import (
    now_utc,
    generate_email_verification_token,
)
from models.db_models import Tenant, TenantEmailVerification
from models.tenant_create import TenantRegisterRequest
from _email_service.sendgrid import email_service
from _email_service.templates import WELCOME_EMAIL_SUBJECT, WELCOME_EMAIL_BODY

from logger import logger
import os

LOGIN_URL = os.getenv("LOGIN_URL" ,"")


async def send_welcome_email(
    tenant_id: str,
    contact_email: str,
    subdomain: str,
    temp_admin_username: str,
    temp_admin_password: str,
):
    body = WELCOME_EMAIL_BODY.format(
        tenant_id=tenant_id,
        # subdomain=subdomain,
        username=temp_admin_username,
        password=temp_admin_password,
        login_url=f"{LOGIN_URL}",
    )

    await email_service.send(
        to_email=contact_email,
        subject=WELCOME_EMAIL_SUBJECT,
        body=body,
    )


async def send_verification_email(contact_email: str, verification_link: str):

    logger.info(f"Sending verification email to {contact_email} with link {verification_link}")

    subject = "Verify your AI4I account"

    text_body = (
        "Welcome to AI4I!\n\n"
        "Please verify your email by clicking the link below:\n"
        f"{verification_link}\n\n"
        "This link expires in 15 minutes."
    )

    html_body = f"""
    <html>
      <body>
        <h2>Welcome to AI4I 🚀</h2>
        <p>Please verify your email address:</p>
        <p>
          <a href="{verification_link}"
             style="padding:10px 16px;background:#2563eb;color:#fff;
                    text-decoration:none;border-radius:6px;">
            Verify Email
          </a>
        </p>
        <p>This link expires in <b>15 mins</b>.</p>
      </body>
    </html>
    """

    await email_service.send(
        to_email=contact_email,
        subject=subject,
        body=text_body,
        html_body=html_body,
    )


