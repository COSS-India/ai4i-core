from fastapi import BackgroundTasks
from datetime import timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from utils.utils import (
    now_utc,
    generate_email_verification_token,
)
from models.db_models import Tenant, TenantEmailVerification
from models.tenant_create import TenantRegisterRequest
from _email_service.amazon_ses import email_service
from _email_service.templates import WELCOME_EMAIL_SUBJECT, WELCOME_EMAIL_BODY ,USER_WELCOME_EMAIL_BODY

from logger import logger
from ai4icore_env import app_env

LOGIN_URL = app_env.login_url
PASSWORD_SETUP_LINK_EXPIRE_HOURS = app_env.email_password_setup_token_expire_hours


async def send_welcome_email(
    tenant_id: str,
    contact_email: str,
    subdomain: str,
    set_password_url: str,
):
    """
    Send welcome email to tenant admin with login credentials after tenant activation.
    
    Args:
        tenant_id: The ID of the tenant
        contact_email: The contact email of the tenant
        subdomain: The tenant's subdomain
        set_password_url: Single-use set-password URL
        login_url: Portal login URL
        email: Admin email address
    """  
    
    body = WELCOME_EMAIL_BODY.format(
            tenant_id=tenant_id,
            email=contact_email,
            login_url=f"{LOGIN_URL}",
            set_password_url=set_password_url,
            setup_link_expiry_hours=PASSWORD_SETUP_LINK_EXPIRE_HOURS,
        )

    html_body = f"""
    <html>
      <body style="font-family:Arial,sans-serif;background:#f8fafc;margin:0;padding:24px;">
        <div style="max-width:640px;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;">
          <div style="padding:20px 24px;background:#0f172a;">
            <h2 style="color:#ffffff;margin:0;">Welcome to AI4I</h2>
          </div>
          <div style="padding:24px;">
            <p style="color:#374151;margin-top:0;">Your tenant has been successfully activated.</p>
            <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:16px;margin:16px 0;">
              <p style="margin:0 0 8px 0;color:#111827;"><b>Tenant ID:</b> {tenant_id}</p>
              <p style="margin:0;color:#111827;"><b>Email ID:</b> {contact_email}</p>
            </div>
            <p style="color:#374151;">
              Click the button below to set your password on the AI4I portal.
            </p>
            <p style="color:#6b7280;font-size:13px;margin:0 0 12px 0;">
              This setup link is valid for <b>{PASSWORD_SETUP_LINK_EXPIRE_HOURS} hours</b> and can be used only once.
            </p>
            <p style="margin:24px 0;">
              <a
                href="{set_password_url}"
                style="display:inline-block;padding:12px 20px;background:#2563eb;color:#ffffff;text-decoration:none;border-radius:8px;font-weight:600;"
              >
                Setup Password
              </a>
            </p>
            <p style="color:#6b7280;font-size:13px;margin:0 0 8px 0;">
              If the button does not work, use this link:
            </p>
            <p style="font-size:13px;word-break:break-all;margin:0 0 8px 0;">
              <a href="{set_password_url}">{set_password_url}</a>
            </p>
            <p style="color:#6b7280;font-size:13px;margin:0 0 8px 0;">
              If this link has expired, please provide your email and contact your platform administrator.
            </p>
            <p style="color:#6b7280;font-size:13px;margin:0;">
              Login URL: <a href="{LOGIN_URL}">{LOGIN_URL}</a>
            </p>
          </div>
        </div>
      </body>
    </html>
    """

    await email_service.send(
        to_email=contact_email,
        subject=WELCOME_EMAIL_SUBJECT,
        body=body,
        html_body=html_body,
    )



async def send_user_welcome_email(
    user_id: str,
    contact_email: str,
    subdomain: str,
    set_password_url: str,
):
    """
    Send welcome email to tenant user with login credentials after user registration.
    
    Args:
        user_id: The ID of the user
        contact_email: The contact email of the user
        subdomain: The tenant's subdomain
        set_password_url: Single-use set-password URL
        email: User email address
    """  
    
    body = USER_WELCOME_EMAIL_BODY.format(
            email=contact_email,
            set_password_url=set_password_url,
            setup_link_expiry_hours=PASSWORD_SETUP_LINK_EXPIRE_HOURS,
        )

    html_body = f"""
    <html>
      <body style="font-family:Arial,sans-serif;background:#f8fafc;margin:0;padding:24px;">
        <div style="max-width:640px;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;">
          <div style="padding:20px 24px;background:#0f172a;">
            <h2 style="color:#ffffff;margin:0;">Welcome to AI4I</h2>
          </div>
          <div style="padding:24px;">
            <p style="color:#374151;margin-top:0;">Your account has been successfully activated.</p>
            <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:16px;margin:16px 0;">
              <p style="margin:0;color:#111827;"><b>Email ID:</b> {contact_email}</p>
            </div>
            <p style="color:#374151;">
              Click the button below to set your password on the AI4I portal.
            </p>
            <p style="color:#6b7280;font-size:13px;margin:0 0 12px 0;">
              This setup link is valid for <b>{PASSWORD_SETUP_LINK_EXPIRE_HOURS} hours</b> and can be used only once.
            </p>
            <p style="margin:24px 0;">
              <a
                href="{set_password_url}"
                style="display:inline-block;padding:12px 20px;background:#2563eb;color:#ffffff;text-decoration:none;border-radius:8px;font-weight:600;"
              >
                Setup Password
              </a>
            </p>
            <p style="color:#6b7280;font-size:13px;margin:0;">
              If the button does not work, use this link:
              <a href="{set_password_url}"> {set_password_url}</a>
            </p>
            <p style="color:#6b7280;font-size:13px;margin:8px 0 0 0;">
              If this link has expired, please provide your email and contact your platform administrator.
            </p>
          </div>
        </div>
      </body>
    </html>
    """

    await email_service.send(
        to_email=contact_email,
        subject=WELCOME_EMAIL_SUBJECT,
        body=body,
        html_body=html_body,
    )


async def send_verification_email(
    contact_email: str, 
    verification_link: str,
    tenant_id: str = None,
    expires_in_minutes: int = None,
):
    """
    Send email verification link to tenant contact email for account activation.

    Args:
        contact_email: The contact email of the tenant
        verification_link: The verification link to be sent
        tenant_id: The tenant identifier (for resend reference)
        expires_in_minutes: How long the verification link remains valid
    """

    logger.info(f"Sending verification email to {contact_email} with link {verification_link}")

    subject = "Verify your AI4I account"
    if expires_in_minutes is None:
        expires_in_minutes = app_env.email_verification_token_expire_minutes

    # Build text body
    text_body = (
        "Welcome to AI4I!\n\n"
        "Please verify your email by clicking the link below:\n"
        f"{verification_link}\n\n"
        f"This link expires in {expires_in_minutes} minutes.\n\n"
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
            To receive the verification email again, please coordinate with the Platform Admin, mention the Tenant ID, 
            and request re-initiation of the email verification process.
          </p>
        </div>
        
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
        <p style="color:#6b7280;">This link expires in <b>{expires_in_minutes} minutes</b>.</p>
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


