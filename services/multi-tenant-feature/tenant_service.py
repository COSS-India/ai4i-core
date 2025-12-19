from fastapi import BackgroundTasks, HTTPException
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
    generate_service_id
)
from models.db_models import Tenant, BillingRecord, AuditLog , TenantEmailVerification , ServiceConfig
from models.enum_tenant import  TenantStatus, AuditAction , BillingStatus , AuditActorType
from models.tenant_create import TenantRegisterRequest, TenantRegisterResponse
from models.service_create import ServiceCreateRequest , ServiceResponse , ListServicesResponse
from models.services_update import ServiceUpdateRequest , FieldChange , ServiceUpdateResponse
from models.billing_update import BillingUpdateRequest, BillingUpdateResponse
from models.tenant_email import TenantResendEmailVerificationResponse

from email_service import send_welcome_email, send_verification_email

from logger import logger
from uuid import UUID
import os
from dotenv import load_dotenv

load_dotenv()

EMAIL_VERIFICATION_LINK = str(os.getenv("EMAIL_VERIFICATION_LINK",""))


# async def send_welcome_email(contact_email: str,  # testing backend function
#     subdomain: str,
#     temp_admin_username: str,
#     temp_admin_password: str,
# ):
#     # How to integrate with real email service?
#     message = (
#         f"Welcome to AI4I!\n\n"
#         f"Tenant Subdomain: {subdomain}\n"
#         f"Admin Username: {temp_admin_username}\n"
#         f"Admin Password: {temp_admin_password}\n\n"
#         f"Login URL: '' "
#     )

#     logger.info(f"Sending welcome email to {contact_email}\n{message}")

# async def send_verification_email(contact_email: str, verification_link: str): -- backend testing function
#     logger.info(
#         f"Sending verification email to {contact_email} with link {verification_link}"
#     )



async def provision_tenant_schema(schema_name: str):
    # create new Postgres schema and run baseline tables/migrations
    # e.g. run alembic migration or raw SQL
    logger.info(f"Provisioning schema: {schema_name}")


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

    # verification_link = f"https://{subdomain}/tenant/verify/email?token={token}" TODO : add subdomain if required

    verification_link = f"http://{EMAIL_VERIFICATION_LINK}/email/verify?token={token}"

    background_tasks.add_task(
        send_verification_email,
        payload.contact_email,
        verification_link
    )
    return token


async def create_new_tenant(
        payload: TenantRegisterRequest,
        db: AsyncSession,
        background_tasks: BackgroundTasks
        ) -> TenantRegisterResponse:

    if payload.contact_email:
        stmt = select(Tenant).where(
            Tenant.contact_email == payload.contact_email,
            Tenant.domain == payload.domain,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Check status
            if existing.status == TenantStatus.PENDING:
                resend = await resend_verification_email(
                    tenant_id=existing.id,
                    db=db,
                    background_tasks=background_tasks,
                )

                return TenantRegisterResponse(
                    id=existing.id,
                    tenant_id=existing.tenant_id,
                    schema_name=existing.schema_name,
                    quotas=existing.quotas,
                    status=existing.status.value,
                    token=resend.token,
                    message="Email verification pending. Link resent , please check your inbox.",
                )
            elif existing.status in [TenantStatus.IN_PROGRESS]:
                raise ValueError("Email already verified")
            elif existing.status == TenantStatus.ACTIVE:
                raise ValueError("Tenant already active")
            elif existing.status == TenantStatus.SUSPENDED:
                raise ValueError("Tenant is suspended. Contact support.")

    # Create new tenant
    tenant_id = generate_tenant_id(payload.organization_name)
    # subdomain = generate_subdomain(tenant_id) # TODO : add subdomain if required
    schema_name = schema_name_from_tenant_id(tenant_id)

    tenant_data = {
        "tenant_id": tenant_id,
        "organization_name": payload.organization_name,
        "contact_email": payload.contact_email,
        "domain": payload.domain,
        # "subdomain": subdomain,
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
    token = await send_verification_link(
        created=created,
        payload=payload,
        db=db,
        subdomain=None,
        background_tasks=background_tasks,
    )

    billing = BillingRecord(
        tenant_id=created.id,
        # billing_plan=payload.billing_plan, # TODO : add billing plan if required
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
            "subscriptions": payload.requested_subscriptions,
            "email": payload.contact_email,
        },
    )
    db.add(audit)

    await db.commit()

    resposne = TenantRegisterResponse(
        id=created.id,
        tenant_id=created.tenant_id,
        schema_name=created.schema_name,
        quotas=created.quotas,
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

    tenant = await db.get(Tenant, verification.tenant_id)
    if not tenant:
        raise ValueError("Tenant not found for this verification token")

    # Check if tenant is already verified/active
    if tenant.status == TenantStatus.ACTIVE:
        raise ValueError("Tenant email already verified")
    
    if tenant.status == TenantStatus.SUSPENDED:
        raise ValueError("Tenant is suspended. Contact support.")

    verification.verified_at = now_utc()
    tenant.status = TenantStatus.ACTIVE

    audit = AuditLog(
        tenant_id=tenant.id,
        action=AuditAction.email_verified,
        actor=AuditActorType.SYSTEM,
        details={
            "organization": tenant.organization_name,
            # "subdomain": tenant.subdomain,
            "subscriptions": tenant.subscriptions,
            "email": tenant.contact_email,
        },
    )
    db.add(audit)

    await db.commit()

    background_tasks.add_task(
        send_welcome_email,
        tenant.contact_email,
        None, # add subdomain if required
        tenant.temp_admin_username,
        tenant.temp_admin_password_hash,
    )

    background_tasks.add_task(
        provision_tenant_schema,
        tenant.schema_name,
    )


async def resend_verification_email(
        tenant_id: UUID,
        db: AsyncSession, 
        background_tasks: BackgroundTasks
        ) -> TenantResendEmailVerificationResponse:
    
    tenant = await db.get(Tenant, tenant_id)

    if not tenant:
        raise ValueError("Tenant not found")

    # Check tenant status - only allow resend if pending or in_progress
    if tenant.status == TenantStatus.ACTIVE:
        raise ValueError("Tenant already verified and active")
    
    if tenant.status == TenantStatus.SUSPENDED:
        raise ValueError("Tenant is suspended. Contact support.")
    
    if tenant.status == TenantStatus.ARCHIVED:
        raise ValueError("Tenant is archived. Contact support.")

    token = generate_email_verification_token()
    expiry = now_utc() + timedelta(minutes=15)  # Match the expiry time from initial verification

    verification = TenantEmailVerification(
        tenant_id=tenant.id,
        token=token,
        expires_at=expiry,
    )
    db.add(verification)
    await db.commit()

    verification_link = f"http://{EMAIL_VERIFICATION_LINK}/email/verify?token={token}"

    background_tasks.add_task(
        send_verification_email,
        tenant.contact_email,
        verification_link,
    )

    logger.info(f"Verification email resent for tenant {tenant.tenant_id} (status: {tenant.status.value})")

    response = TenantResendEmailVerificationResponse(
        tenant_uuid=tenant.id,
        tenant_id=tenant.tenant_id,
        token=token,
        message="Verification email resent successfully",
    )

    return response


async def create_service(payload: ServiceCreateRequest,db: AsyncSession,) -> ServiceResponse:

    existing = await db.execute(
        select(ServiceConfig)
        .where(ServiceConfig.service_name == payload.service_name)
    )

    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Service '{payload.service_name}' already exists",
        )

    for _ in range(3):
        service_id = generate_service_id()

        exists = await db.execute(
            select(ServiceConfig.id)
            .where(ServiceConfig.id == service_id)
        )

        if not exists.scalar_one_or_none():
            break
    else:
        raise HTTPException(status_code=500, detail="Failed to generate unique service ID")

    service = ServiceConfig(
        id=service_id,
        service_name=payload.service_name,
        unit_type=payload.unit_type,
        price_per_unit=payload.price_per_unit,
        currency=payload.currency,
    )

    db.add(service)
    await db.commit()
    await db.refresh(service)

    response  = ServiceResponse(
            id=service.id,
            service_name=service.service_name,
            unit_type=service.unit_type.value,
            price_per_unit=service.price_per_unit,
            currency=service.currency,
            is_active=service.is_active,
            created_at=service.created_at,
            updated_at=service.updated_at,
        )

    return response




async def update_service(payload: ServiceUpdateRequest,db: AsyncSession,) -> ServiceUpdateResponse:

    service = await db.get(ServiceConfig, payload.service_id)

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    update_data = payload.model_dump(exclude_unset=True)

    # Remove service_id from update payload since it is not needed in update data
    update_data = payload.model_dump(
        exclude_unset=True,
        exclude={"service_id"}
    )

    changes = {}

    for field, new_value in update_data.items():
        old_value = getattr(service, field)

        if old_value != new_value:
            changes[field] = FieldChange(
                old=old_value,
                new=new_value,
            )
            setattr(service, field, new_value)

    await db.commit()
    await db.refresh(service)

    logger.info(f"Service pricing updated. Service ID={service.id}, Changes={changes}")

    return ServiceUpdateResponse(
        message="Service pricing updated successfully",
        service=ServiceResponse(
            id=service.id,
            service_name=service.service_name,
            unit_type=service.unit_type.value,
            price_per_unit=float(service.price_per_unit),
            currency=service.currency,
            is_active=service.is_active,
            created_at=service.created_at,
            updated_at=service.updated_at,
        ),
        changes=changes,
    )



async def list_service(db: AsyncSession) -> ListServicesResponse:
    result = await db.execute(
        select(ServiceConfig).where(ServiceConfig.is_active.is_(True))
    )

    services = result.scalars().all()

    return ListServicesResponse(
        count=len(services),
        services=[
            ServiceResponse(
                id=s.id,
                service_name=s.service_name,
                unit_type=s.unit_type,
                price_per_unit=float(s.price_per_unit),
                currency=s.currency,
                is_active=s.is_active,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in services
        ],
    )



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

