from fastapi import BackgroundTasks, HTTPException
from datetime import datetime, timezone , timedelta , date

from sqlalchemy import insert , select , update
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
    generate_service_id,
    generate_random_password,
    hash_password,
)
from models.db_models import (
    Tenant, 
    BillingRecord, 
    AuditLog , 
    TenantEmailVerification , 
    ServiceConfig,
    TenantUser,
    UserBillingRecord,
)
from models.auth_models import UserDB
from models.enum_tenant import  TenantStatus, AuditAction , BillingStatus , AuditActorType , TenantUserStatus
from models.tenant_create import TenantRegisterRequest, TenantRegisterResponse
from models.service_create import ServiceCreateRequest , ServiceResponse , ListServicesResponse
from models.user_create import UserRegisterRequest, UserRegisterResponse
from models.services_update import ServiceUpdateRequest , FieldChange , ServiceUpdateResponse
from models.billing_update import BillingUpdateRequest, BillingUpdateResponse
from models.tenant_email import TenantResendEmailVerificationResponse
from models.tenant_subscription import TenantSubscriptionResponse
from models.tenant_status import TenantStatusUpdateRequest , TenantStatusUpdateResponse
from models.user_status import TenantUserStatusUpdateRequest , TenantUserStatusUpdateResponse

from email_service import send_welcome_email, send_verification_email , send_user_welcome_email

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

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"Integrity error while creating verification token for tenant {created.id}: {e}")
        raise HTTPException(status_code=409,detail="Verification token creation failed")
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error committing verification token to database: {e}")
        raise HTTPException(status_code=500,detail="Failed to create verification token")

    # verification_link = f"https://{subdomain}/tenant/verify/email?token={token}" TODO : add subdomain if required

    verification_link = f"{EMAIL_VERIFICATION_LINK}/email/verify?token={token}"

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
        "temp_admin_username": "",
        "temp_admin_password_hash": "",
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

    try:
        await db.commit()
    except IntegrityError as e:
        logger.error(f"Integrity error while creating tenant {tenant_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=409,detail="Tenant creation failed")
    except Exception as e:
        logger.exception(f"Error committing tenant creation to database: {e}")
        await db.rollback()
        raise HTTPException(status_code=500,detail="Failed to create tenant")

    resposne = TenantRegisterResponse(
        id=created.id,
        tenant_id=created.tenant_id,
        schema_name=created.schema_name,
        subscriptions=created.subscriptions,
        quotas=created.quotas,
        status=created.status.value if hasattr(created.status, "value") else str(created.status),
        token=token,
    )

    return resposne



async def verify_email_token(token: str, tenant_db: AsyncSession, auth_db: AsyncSession, background_tasks: BackgroundTasks):

    stmt = select(TenantEmailVerification).where(
        TenantEmailVerification.token == token,
        TenantEmailVerification.verified_at.is_(None)
    )
    verification = (await tenant_db.execute(stmt)).scalar_one_or_none()

    if not verification:
        raise ValueError("Invalid or expired token")

    if verification.expires_at < now_utc():
        raise ValueError("Token expired")

    tenant = await tenant_db.get(Tenant, verification.tenant_id)
    if not tenant:
        raise ValueError("Tenant not found for this verification token")

    # Check if tenant is already verified/active
    if tenant.status == TenantStatus.ACTIVE:
        raise ValueError("Tenant email already verified")
    
    if tenant.status == TenantStatus.SUSPENDED:
        raise ValueError("Tenant is suspended. Contact support.")

    verification.verified_at = now_utc()
    tenant.status = TenantStatus.ACTIVE

    #generate username and password

    admin_username = f"admin@{tenant.tenant_id}"
    plain_password = generate_random_password(length = 8)
    logger.debug(f"Password generated for Tenant(uuid):-{tenant.id} | Tenant:- {tenant.tenant_id}")
    hashed_password = hash_password(plain_password)

    tenant.temp_admin_username = admin_username
    tenant.temp_admin_password_hash = hashed_password
    
    admin_user = UserDB(
            email=tenant.contact_email,
            username=admin_username,
            hashed_password=hashed_password,
            is_active=True,
            is_verified=True,
        )
    auth_db.add(admin_user)


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
    tenant_db.add(audit)

    try:
        await auth_db.commit()
    except IntegrityError as e:
        logger.error(f"Integrity error while committing admin user to auth_db for tenant {tenant.tenant_id}: {e}")
        await auth_db.rollback()
        raise HTTPException(status_code=409, detail="Failed to create admin user")
    except Exception as e:
        logger.exception(f"Error committing admin user to auth_db: {e}")
        await auth_db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create admin user in authentication database")

    try:
        await tenant_db.commit()
    except IntegrityError as e:
        logger.error(f"Integrity error while committing tenant verification to tenant_db for tenant {tenant.tenant_id}: {e}")
        await tenant_db.rollback()
        raise HTTPException(status_code=409, detail="Failed to verify tenant")
    except Exception as e:
        logger.exception(f"Error committing tenant verification to tenant_db: {e}")
        await tenant_db.rollback()
        raise HTTPException(status_code=500, detail="Failed to verify tenant in database")

    await tenant_db.refresh(tenant)

    # Extract values before adding background task to avoid detached object issues
    tenant_id_str = str(tenant.tenant_id)
    contact_email_str = str(tenant.contact_email)
    admin_username_str = str(tenant.temp_admin_username) if tenant.temp_admin_username else admin_username
    password_str = str(plain_password)

    logger.info(f"Tenant verified and activated: {tenant_id_str}")

    background_tasks.add_task(
        send_welcome_email,
        tenant_id_str,
        contact_email_str,
        None,  # subdomain not available
        admin_username_str,
        password_str,
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
    
    # if tenant.status == TenantStatus.ARCHIVED:
    #     raise ValueError("Tenant is archived. Contact support.")

    token = generate_email_verification_token()
    expiry = now_utc() + timedelta(minutes=15)  # Match the expiry time from initial verification

    verification = TenantEmailVerification(
        tenant_id=tenant.id,
        token=token,
        expires_at=expiry,
    )
    db.add(verification)
    
    try:
        await db.commit()
    except IntegrityError as e:
        logger.error(f"Integrity error while resending verification email for tenant {tenant.tenant_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=409, detail="Failed to create verification token")
    except Exception as e:
        logger.exception(f"Error committing verification token resend to database: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to resend verification email")

    # verification_link = f"https://{tenant.subdomain}/verify-email?token={token}" # TODO : add subdomain if required

    verification_link = f"http://{EMAIL_VERIFICATION_LINK}/email/verify?token={token}"

    # Extract email before adding background task to avoid detached object issues
    contact_email_str = str(tenant.contact_email)

    background_tasks.add_task(
        send_verification_email,
        contact_email_str,
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
    
    try:
        await db.commit()
        await db.refresh(service)
    except IntegrityError as e:
        logger.error(f"Integrity error while creating service {payload.service_name}: {e}")
        await db.rollback()
        raise HTTPException(status_code=409,detail=f"Service creation failed - service '{payload.service_name}' or ID {service_id} may already exist")
    except Exception as e:
        logger.exception(f"Error committing service creation to database: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create service")

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

    try:
        await db.commit()
        await db.refresh(service)
    except IntegrityError as e:
        logger.error(f"Integrity error while updating service {payload.service_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=409, detail="Service update failed"
        )
    except Exception as e:
        logger.exception(f"Error committing service update to database: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update service")

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



async def add_subscriptions(tenant_id: str,subscriptions: list[str],db: AsyncSession,) -> TenantSubscriptionResponse:
    """
    Add subscriptions to a tenant.
    Fails if subscription already exists.
    """

    tenant = await db.scalar(select(Tenant).where(Tenant.tenant_id == tenant_id))

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if tenant.status != TenantStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Tenant is not active")

    # Validate services
    valid_services = await db.scalars(
        select(ServiceConfig.service_name)
        .where(ServiceConfig.is_active.is_(True))
    )
    valid_services = set(valid_services.all())

    print(valid_services)

    invalid = set(subscriptions) - valid_services
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid subscriptions: {list(invalid)}",
        )

    current = set(tenant.subscriptions or [])
    duplicates = current & set(subscriptions)

    if duplicates:
        raise HTTPException(
            status_code=400,
            detail=f"Subscription(s) already exist: {list(duplicates)}",
        )

    updated = list(current | set(subscriptions))
    tenant.subscriptions = updated

    # Audit log
    db.add(
        AuditLog(
            tenant_id=tenant.id,
            action=AuditAction.subscription_added,
            details={"added": subscriptions},
        )
    )

    try:
        await db.commit()
        await db.refresh(tenant)
    except IntegrityError as e:
        logger.error(f"Integrity error while adding subscriptions for tenant {tenant.tenant_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=409, detail="Failed to add subscriptions")
    except Exception as e:
        logger.exception(f"Error committing subscription changes to database for tenant {tenant.tenant_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to add subscriptions")

    return TenantSubscriptionResponse(
        tenant_id=tenant.tenant_id,
        subscriptions=tenant.subscriptions,
    )





async def remove_subscriptions(tenant_id: str,subscriptions: list[str],db: AsyncSession,) -> TenantSubscriptionResponse:

    tenant = await db.scalar(select(Tenant).where(Tenant.tenant_id == tenant_id))

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    current = set(tenant.subscriptions or [])
    to_remove = set(subscriptions)

    # Validate: subscriptions must exist
    missing = to_remove - current
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Subscriptions not present for tenant: {list(missing)}",
        )
    
    updated = list(current - set(subscriptions))
    tenant.subscriptions = updated

    db.add(
        AuditLog(
            tenant_id=tenant.id,
            action=AuditAction.subscription_removed,
            details={"removed": subscriptions},
        )
    )

    try:
        await db.commit()
        await db.refresh(tenant)
    except IntegrityError as e:
        logger.error(f"Integrity error while removing subscriptions for tenant {tenant.tenant_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=409, detail="Failed to remove subscriptions")
    except Exception as e:
        logger.exception(f"Error committing subscription removal to database for tenant {tenant.tenant_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to remove subscriptions")

    return TenantSubscriptionResponse(
        tenant_id=tenant.tenant_id,
        subscriptions=tenant.subscriptions,
    )





async def register_user(
    payload: UserRegisterRequest,
    tenant_db: AsyncSession,
    auth_db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> UserRegisterResponse:
    """
    Register a user under a tenant and create billing records
    """

    tenant = await tenant_db.scalar(select(Tenant).where(Tenant.tenant_id == payload.tenant_id))

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if tenant.status != TenantStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Tenant is not active")

    # Validate services against tenant subscriptions
    tenant_services = set(tenant.subscriptions or [])
    requested_services = set(payload.services)

    if not requested_services:
        raise HTTPException(status_code=400, detail="At least one service is required")
    
    inactive_services = set(requested_services) - tenant_services
    if not requested_services.issubset(tenant_services):
        raise HTTPException(
            status_code=400,
            detail=f"One or more services are not enabled for this tenant {inactive_services}",
        )

    # Validate services are active
    services = await tenant_db.scalars(
        select(ServiceConfig).where(
            ServiceConfig.service_name.in_(requested_services),
            ServiceConfig.is_active.is_(True),
        )
    )
    services = services.all()

    if len(services) != len(requested_services):
        raise HTTPException(
            status_code=400,
            detail=f"One or more services are invalid or inactive services : {inactive_services}")
    
    # Check if user already exists under this tenant
    existing_tenant_user = await tenant_db.scalar(
    select(TenantUser).where(TenantUser.email == payload.email))

    if existing_tenant_user:
        raise HTTPException(status_code=409,detail="User already registered under this tenant")

    # Generate / hash password
    plain_password = payload.password or generate_random_password(length=12)
    hashed_password = hash_password(plain_password)

    # Create user in AUTH DB
    user = UserDB(
        email=payload.email,
        username=payload.username,
        hashed_password=hashed_password,
        is_active=True,
        is_verified=True,
    )

    try:
        auth_db.add(user)
        await auth_db.commit()
        await auth_db.refresh(user)
    except Exception as e:
        await auth_db.rollback()
        logger.error(f"Failed to create user in auth DB: {e}")
        raise HTTPException(status_code=409, detail="User already exists")
    
    if payload.is_approved:
        #Create TenantUser entry only if user is approved
        tenant_user = TenantUser(
                user_id=user.id,
                tenant_uuid=tenant.id,
                tenant_id=tenant.tenant_id,
                username=payload.username,
                email=payload.email,
                subscriptions=list(requested_services),
                status=TenantUserStatus.ACTIVE, 
                is_approved=True,
        )
    else:
        raise HTTPException(status_code=400, detail="User must be approved by tenant admin to register")

    tenant_db.add(tenant_user)
    await tenant_db.flush()

    # 6️⃣ Create UserBillingRecord entries (TENANT DB)
    billing_month = date.today().replace(day=1)

    #TODO: commenting this out , need to check billing logic

    for service in services:
        tenant_db.add(
            UserBillingRecord(
                user_id=tenant_user.id,
                tenant_id=tenant.tenant_id,
                service_id=service.id,
                service_name=service.service_name,
                cost=0,
                billing_period=billing_month,
                status=TenantUserStatus.ACTIVE
        )
    )

    tenant_db.add(
        AuditLog(
            tenant_id=tenant.id,
            action=AuditAction.user_created,
            actor=AuditActorType.SYSTEM,
            details={
                "username": payload.username,
                "email": payload.email,
                "services": list(requested_services),
            },
        )
    )

    try:
        await tenant_db.commit()
    except IntegrityError as e:
        logger.error(f"Integrity error while registering user {payload.username} for tenant {tenant.tenant_id}: {e}")
        await tenant_db.rollback()
        raise HTTPException(status_code=409, detail="User registration failed")
    except Exception as e:
        logger.exception(f"Error committing user registration to database: {e}")
        await tenant_db.rollback()
        raise HTTPException(status_code=500, detail="Failed to register user")


    background_tasks.add_task(
        send_user_welcome_email,
        user.id,
        payload.email,
        None,  # add subdomain if required
        payload.username,
        plain_password,
    )

    logger.info(
        f"User registered successfully | tenant={tenant.tenant_id} | user={payload.username}"
    )

    response = UserRegisterResponse(
        user_id=user.id,
        tenant_id=tenant.tenant_id,
        username=user.username,
        email=user.email,
        services=list(requested_services),
        created_at=user.created_at,
    )

    return response


async def update_tenant_status(payload: TenantStatusUpdateRequest, db: AsyncSession) -> TenantStatusUpdateResponse:
    """
    Update tenant status and cascade to tenant users and billing records.
    """
    tenant = await db.scalar(select(Tenant).where(Tenant.tenant_id == payload.tenant_id))

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    old_status = tenant.status
    new_status = payload.status

    if old_status == new_status:
        raise HTTPException(
            status_code=400,
            detail=f"Tenant already in {new_status} state",
        )

    tenant.status = new_status

    # Cascade user status for this tenant
    if new_status == TenantStatus.SUSPENDED:
        await db.execute(
            update(TenantUser)
            .where(TenantUser.tenant_id == payload.tenant_id)
            .values(status=TenantUserStatus.SUSPENDED)
        )
        # Mark all user billing records for this tenant as suspended
        await db.execute(
            update(UserBillingRecord)
            .where(UserBillingRecord.tenant_id == payload.tenant_id)
            .values(status=TenantUserStatus.SUSPENDED)
        )
    elif new_status == TenantStatus.ACTIVE:
        await db.execute(
            update(TenantUser)
            .where(TenantUser.tenant_id == payload.tenant_id)
            .values(status=TenantUserStatus.ACTIVE)
        )
        # Reactivate user billing records
        await db.execute(
            update(UserBillingRecord)
            .where(UserBillingRecord.tenant_id == payload.tenant_id)
            .values(status=TenantUserStatus.ACTIVE)
        )

    # Update tenant-level billing record status if it exists
    billing_record = await db.scalar(select(BillingRecord).where(BillingRecord.tenant_id == tenant.id))
    if billing_record:
        if new_status == TenantStatus.SUSPENDED:
            billing_record.billing_status = BillingStatus.OVERDUE
            billing_record.suspension_reason = payload.reason if payload.reason else ""
            billing_record.suspended_until = payload.suspended_until or None
        elif new_status == TenantStatus.ACTIVE:
            # When reactivating, mark as UNPAID if it was overdue/pending
            if billing_record.billing_status in {
                BillingStatus.OVERDUE,
                BillingStatus.UNPAID,
                BillingStatus.PENDING,
            }:
                billing_record.billing_status = BillingStatus.PAID
            billing_record.suspension_reason = None
            billing_record.suspended_until = None

    # Audit log for tenant status change
    db.add(
        AuditLog(
            tenant_id=tenant.id,
            action=(
                AuditAction.tenant_suspended
                if new_status == TenantStatus.SUSPENDED
                else AuditAction.tenant_updated
            ),
            actor=AuditActorType.SYSTEM,
            details={
                "old_status": old_status,
                "new_status": new_status,
                "reason": payload.reason,
            },
        )
    )

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"Integrity error while updating tenant status | tenant={payload.tenant_id}: {e}")
        raise HTTPException(status_code=409, detail="Tenant status update failed")
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error committing tenant status update to database | tenant={payload.tenant_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update tenant status")
    
    response = TenantStatusUpdateResponse(
        tenant_id=tenant.tenant_id,
        old_status=old_status,
        new_status=new_status,
    )

    return response



async def update_tenant_user_status(payload: TenantUserStatusUpdateRequest, db: AsyncSession):
    """
    Update a tenant user's status and cascade to their billing records.
    """
    tenant_id = payload.tenant_id
    user_id = payload.user_id

    tenant = await db.scalar(select(Tenant).where(Tenant.tenant_id == tenant_id))

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if tenant.status == TenantStatus.SUSPENDED:
        raise HTTPException(
            status_code=400,
            detail="Cannot update user status while tenant is suspended",
        )
    
    tenant_user = await db.scalar(select(TenantUser).where(TenantUser.tenant_id == tenant_id,TenantUser.user_id == user_id))

    if not tenant_user:
        raise HTTPException(status_code=404, detail="Tenant user not found")

    if tenant_user.status == payload.status:
        raise HTTPException(
            status_code=400,
            detail=f"User already {payload.status}",
        )

    old_status = tenant_user.status
    tenant_user.status = payload.status

    # Cascade status to this user's billing records
    await db.execute(update(UserBillingRecord)
        .where(
            UserBillingRecord.tenant_id == tenant_id,
            UserBillingRecord.user_id == tenant_user.id,
        )
        .values(status=payload.status)
    )

    # Audit log
    db.add(
        AuditLog(
            tenant_id=tenant_user.tenant_uuid,
            action=AuditAction.user_updated,
            actor=AuditActorType.ADMIN,
            details={
                "user_id": user_id,
                "old_status": old_status,
                "new_status": payload.status,
            },
        )
    )

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"Integrity error while updating tenant user status | tenant={tenant_id} user_id={user_id}: {e}")
        raise HTTPException(status_code=409, detail="Tenant user status update failed")
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error committing tenant user status update to database | tenant={tenant_id} user_id={user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update tenant user status")

    response = TenantUserStatusUpdateResponse(
        tenant_id=tenant_id,
        user_id=user_id,
        old_status=old_status,
        new_status=payload.status,
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

    try:
        await db.commit()
        await db.refresh(billing)
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"Integrity error while updating billing plan for tenant {payload.tenant_id}: {e}")
        raise HTTPException(
            status_code=409,
            detail="Billing plan update failed due to integrity constraint violation"
        )
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error committing billing plan update to database: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to update billing plan"
        )

    return BillingUpdateResponse(
        tenant_id=billing.tenant_id,
        billing_customer_id=billing.billing_customer_id,
        billing_plan=billing.billing_plan,
        billing_status=billing.billing_status.value,
    )

