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
from _email_service.templates import WELCOME_EMAIL_SUBJECT, WELCOME_EMAIL_BODY ,USER_WELCOME_EMAIL_BODY

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
    """
    Send welcome email to tenant admin with login credentials after tenant activation.
    
    Args:
        tenant_id: The ID of the tenant
        contact_email: The contact email of the tenant
        subdomain: The tenant's subdomain
        temp_admin_username: Temporary admin username
        temp_admin_password: Temporary admin password
        email: Admin email address
    """  
    
    body = WELCOME_EMAIL_BODY.format(
            tenant_id=tenant_id,
            # subdomain=subdomain,
            username=temp_admin_username,
            password=temp_admin_password,
            email=contact_email,
            login_url=f"{LOGIN_URL}",
        )

    await email_service.send(
        to_email=contact_email,
        subject=WELCOME_EMAIL_SUBJECT,
        body=body,
    )



async def send_user_welcome_email(
    user_id: str,
    contact_email: str,
    subdomain: str,
    temp_username: str,
    temp_password: str,
):
    """
    Send welcome email to tenant user with login credentials after user registration.
    
    Args:
        user_id: The ID of the user
        contact_email: The contact email of the user
        subdomain: The tenant's subdomain
        temp_username: Temporary username
        temp_password: Temporary password
        email: User email address
    """  
    
    body = USER_WELCOME_EMAIL_BODY.format(
            user_id=user_id,
            # subdomain=subdomain,
            username=temp_username,
            password=temp_password,
            email=contact_email,
            login_url=f"{LOGIN_URL}",
        )

    await email_service.send(
        to_email=contact_email,
        subject=WELCOME_EMAIL_SUBJECT,
        body=body,
    )


async def send_verification_email(
    contact_email: str, 
    verification_link: str,
    tenant_id: str = None,
):
    """
    Send email verification link to tenant contact email for account activation.

    Args:
        contact_email: The contact email of the tenant
        verification_link: The verification link to be sent
        tenant_id: The tenant identifier (for resend reference)
    """

    logger.info(f"Sending verification email to {contact_email} with link {verification_link}")

    subject = "Verify your AI4I account"

    # Build text body
    text_body = (
        "Welcome to AI4I!\n\n"
        "Please verify your email by clicking the link below:\n"
        f"{verification_link}\n\n"
        "This link expires in 15 minutes.\n\n"
    )
    if tenant_id:
        text_body += f"Your Tenant ID: {tenant_id}\n\n"
        text_body += "If the verification link expires, use your Tenant ID to request a new one.\n"

    # Build HTML body with resend section
    resend_section = ""
    if tenant_id:
        resend_section = f"""
        <hr style="margin:24px 0;border:none;border-top:1px solid #e5e7eb;">
        <div style="background:#f9fafb;padding:16px;border-radius:8px;">
          <p style="margin:0 0 8px 0;color:#374151;font-weight:600;">Link expired?</p>
          <p style="margin:0 0 12px 0;color:#6b7280;font-size:14px;">
            Your Tenant ID: <code style="background:#e5e7eb;padding:2px 8px;border-radius:4px;font-family:monospace;">{tenant_id}</code>
          </p>
          <p style="margin:0;color:#6b7280;font-size:13px;">
            To resend the verification email, visit the registration page and click "Resend Verification Email", 
            then enter your Tenant ID above.
          </p>
        </div>
        
        <!-- 
        FRONTEND IMPLEMENTATION NOTE:
        ==============================
        To implement the "Resend Verification Email" feature on your frontend:
        
        1. Create a page/modal with an input field for "Tenant ID"
        2. On submit, call the API:
           
           POST /api/v1/multi-tenant/email/resend
           Content-Type: application/json
           
           {{"tenant_id": "{tenant_id}"}}
        
        3. Handle the response:
           - Success (201): Show "Verification email sent!" message
           - Error (400/404): Show "Tenant not found" or validation error
           - Error (409): Show "Tenant already verified"
        -->
        """

    html_body = f"""
    <html>
      <body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
        <h2 style="color:#1f2937;">Welcome to AI4I </h2>
        <p style="color:#374151;">Please verify your email address to activate your account:</p>
        <p style="margin:24px 0;">
          <a href="{verification_link}"
             style="padding:12px 24px;background:#2563eb;color:#fff;
                    text-decoration:none;border-radius:6px;display:inline-block;font-weight:500;">
            Verify Email
          </a>
        </p>
        <p style="color:#6b7280;">This link expires in <b>15 minutes</b>.</p>
        {resend_section}
      </body>
    </html>
    """

    await email_service.send(
        to_email=contact_email,
        subject=subject,
        body=text_body,
        html_body=html_body,
    )


