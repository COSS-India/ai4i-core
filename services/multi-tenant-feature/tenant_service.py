from fastapi import BackgroundTasks
from datetime import datetime, timezone , timedelta

from sqlalchemy import insert , select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError , NoResultFound

from utils.utils import (
    generate_tenant_id,
    generate_subdomain,
    schema_name_from_tenant_id,
    DEFAULT_QUOTAS,
    now_utc,
    generate_billing_customer_id,
    generate_email_verification_token,
)
from models.db_models import Tenant, BillingRecord, AuditLog , TenantEmailVerification
from models.enum_tenant import  TenantStatus, AuditAction , BillingStatus , AuditActorType
from models.tenant_create import TenantRegisterRequest, TenantRegisterResponse
from models.billing_update import BillingUpdateRequest, BillingUpdateResponse
from models.tenant_email import TenantResendEmailVerificationResponse

from logger import logger


async def send_welcome_email(contact_email: str,
    subdomain: str,
    temp_admin_username: str,
    temp_admin_password: str,
):
    # How to integrate with real email service?
    message = (
        f"Welcome to AI4I!\n\n"
        f"Tenant Subdomain: {subdomain}\n"
        f"Admin Username: {temp_admin_username}\n"
        f"Admin Password: {temp_admin_password}\n\n"
        f"Login URL: '' "
    )

    logger.info(f"Sending welcome email to {contact_email}\n{message}")

async def provision_tenant_schema(schema_name: str):
    # create new Postgres schema and run baseline tables/migrations
    # e.g. run alembic migration or raw SQL
    logger.info(f"Provisioning schema: {schema_name}")

async def send_verification_email(contact_email: str, verification_link: str):
    logger.info(
        f"Sending verification email to {contact_email} with link {verification_link}"
    )


async def send_verification_link(
        created: Tenant, 
        payload: TenantRegisterRequest, 
        db: AsyncSession, 
        subdomain: str, 
        background_tasks: BackgroundTasks
        ):

    token = generate_email_verification_token()
    expiry = now_utc() + timedelta(minutes=15)

    verification = TenantEmailVerification(
        tenant_id=created.id,
        token=token,
        expires_at=expiry,
    )
    db.add(verification)

    await db.commit()

    verification_link_prod = f"https://{subdomain}/tenant/verify/email?token={token}"

    verification_link_dev = f"http://localhost:8001/tenant/verify/email?token={token}"

    print("Production verification link:", verification_link_prod)

    print("Development verification link:", verification_link_dev)

    background_tasks.add_task(
        send_verification_email,
        payload.contact_email,
        verification_link_dev
    )
    return token


async def create_new_tenant(
        payload: TenantRegisterRequest,
        db: AsyncSession,
        background_tasks: BackgroundTasks
        ) -> TenantRegisterResponse:


    if payload.contact_email:
        stmt = select(Tenant.id).where(Tenant.contact_email == payload.contact_email)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            raise ValueError("Tenant with this contact email already exists")
        
    tenant_id = generate_tenant_id(payload.organization_name)
    subdomain = generate_subdomain(tenant_id)
    schema_name = schema_name_from_tenant_id(tenant_id)

    # Build tenant record
    tenant_data = {
        "tenant_id": tenant_id,
        "organization_name": payload.organization_name,
        "contact_email": payload.contact_email,
        "domain": payload.domain,
        "subdomain": subdomain,
        "schema_name": schema_name,
        "subscriptions": payload.requested_subscriptions or [],
        "quotas": payload.requested_quotas or DEFAULT_QUOTAS,
        "status": TenantStatus.PENDING,
        "temp_admin_username": f"admin@{tenant_id}",
        "temp_admin_password_hash": "TO_BE_HASHED",
    }

    
    stmt = insert(Tenant).values(**tenant_data).returning(Tenant)
    result = await db.execute(stmt)
    created: Tenant = result.scalar_one()

    # Email verification
    token = await send_verification_link(created, payload, db, subdomain , background_tasks)

    
    billing = BillingRecord(
        tenant_id=created.id,
        billing_plan=payload.billing_plan,
        billing_customer_id=generate_billing_customer_id(str(tenant_id)),
        suspension_reason=None,
        suspended_until=None,
    )
    db.add(billing)

    # Insert AuditLog
    audit = AuditLog(
        tenant_id=created.id,
        action=AuditAction.tenant_created,
        actor=AuditActorType.SYSTEM,
        details={
            "organization": payload.organization_name,
            "subdomain": subdomain,
            "subscriptions": payload.requested_subscriptions,
            "email": payload.contact_email,
        },
    )
    db.add(audit)

    await db.commit()

    resposne = TenantRegisterResponse(
        id=created.id,
        tenant_id=created.tenant_id,
        subdomain=created.subdomain,
        schema_name=created.schema_name,
        validation_time=now_utc(),
        status=created.status.value if hasattr(created.status, "value") else str(created.status),
        token=token,
    )

    return resposne


async def verify_email_token(token: str, db: AsyncSession, background_tasks):
    stmt = select(TenantEmailVerification).where(
        TenantEmailVerification.token == token,
        TenantEmailVerification.verified_at.is_(None)
    )
    verification = (await db.execute(stmt)).scalar_one_or_none()

    if not verification:
        raise ValueError("Invalid or expired token")

    if verification.expires_at < now_utc():
        raise ValueError("Token expired")

    verification.verified_at = now_utc()

    tenant = await db.get(Tenant, verification.tenant_id)
    tenant.status = TenantStatus.IN_PROGRESS

    audit = AuditLog(
        tenant_id=tenant.id,
        action=AuditAction.email_verified,
        actor=AuditActorType.SYSTEM,
        details={
            "organization": tenant.organization_name,
            "subdomain": tenant.subdomain,
            "subscriptions": tenant.subscriptions,
            "email": tenant.contact_email,
        },
    )
    db.add(audit)

    await db.commit()

    background_tasks.add_task(
        send_welcome_email,
        tenant.contact_email,
        tenant.subdomain,
        tenant.temp_admin_username,
        tenant.temp_admin_password_hash,
    )

    background_tasks.add_task(
        provision_tenant_schema,
        tenant.schema_name,
    )


async def resend_verification_email(
    tenant_id: str,
    db: AsyncSession,
    background_tasks,
):
    tenant = await db.get(Tenant, tenant_id)

    if not tenant:
        raise ValueError("Tenant not found")

    if tenant.status == TenantStatus.ACTIVE:
        raise ValueError("Tenant already verified")

    token = generate_email_verification_token()

    verification = TenantEmailVerification(
        tenant_id=tenant.id,
        token=token,
        expires_at=now_utc() + timedelta(hours=24),
    )
    db.add(verification)
    await db.commit()

    verification_link_prod = f"https://{tenant.subdomain}/verify-email?token={token}"

    verification_link_dev = f"http://localhost:8001/tenant/verify/email?token={token}"

    print("Production verification link:", verification_link_prod)

    print("Development verification link:", verification_link_dev)

    background_tasks.add_task(
        send_verification_email,
        tenant.contact_email,
        verification_link_dev,
    )

    response = TenantResendEmailVerificationResponse(
        tenant_uuid=tenant.id,
        tenant_id=tenant.tenant_id,
        token=token,
        message="Verification email resent successfully",
    )

    return response




async def update_billing_plan(db: AsyncSession,payload: BillingUpdateRequest) -> BillingUpdateResponse:

    stmt = select(BillingRecord).where(BillingRecord.tenant_id == payload.tenant_id)
    result = await db.execute(stmt)
    billing: BillingRecord | None = result.scalar_one_or_none()

    if not billing:
        raise NoResultFound()

    if not billing.billing_customer_id:
        billing.billing_customer_id = generate_billing_customer_id(str(payload.tenant_id))

    billing.billing_plan = payload.billing_plan
    billing.billing_status = BillingStatus.PENDING.value  # TODO payment yet to be confirmed

    # Audit log
    audit = AuditLog(
        tenant_id=payload.tenant_id,
        action=AuditAction.billing_updated,
        actor="user",
        details={
            "billing_plan": str(payload.billing_plan),
            "billing_status": billing.billing_status,
        },
    )
    db.add(audit)

    await db.commit()
    await db.refresh(billing)

    return BillingUpdateResponse(
        tenant_id=billing.tenant_id,
        billing_customer_id=billing.billing_customer_id,
        billing_plan=billing.billing_plan,
        billing_status=billing.billing_status.value,
    )

