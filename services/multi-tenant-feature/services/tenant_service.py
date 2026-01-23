from fastapi import BackgroundTasks, HTTPException
from datetime import datetime, timezone , timedelta , date

from typing import Optional
from sqlalchemy import insert , select , update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError , NoResultFound

import os
import httpx

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
from models.tenant_view import TenantViewResponse
from models.user_view import TenantUserViewResponse

from services.email_service import send_welcome_email, send_verification_email , send_user_welcome_email

from logger import logger
from uuid import UUID
from dotenv import load_dotenv

load_dotenv()

EMAIL_VERIFICATION_LINK = str(os.getenv("EMAIL_VERIFICATION_LINK",""))
DB_NAME                 = str(os.getenv("APP_DB_NAME", "multi_tenant_db"))
API_GATEWAY_URL        = str(os.getenv("API_GATEWAY_URL", "http://api-gateway-service:8080"))
API_GATEWAY_TIMEOUT       = float(os.getenv("API_GATEWAY_TIMEOUT", "10"))


# Service to table mapping - maps service names to their corresponding table names (__tablename__)
# These are the actual table names as defined in the models, not the class names
SERVICE_TABLE_MAPPING = {
    "nmt": ["nmt_requests", "nmt_results"],
    "tts": ["tts_requests", "tts_results"],
    "asr": ["asr_requests", "asr_results"],
    "ocr": ["ocr_requests", "ocr_results"],
    "ner": ["ner_requests", "ner_results"],
    "llm": ["llm_requests", "llm_results"],
    "transliteration": ["transliteration_requests", "transliteration_results"],
    "language_detection": ["language_detection_requests", "language_detection_results"],
    "speaker_diarization": ["speaker_diarization_requests", "speaker_diarization_results"],
    "audio_language_detection": ["audio_lang_detection_requests", "audio_lang_detection_results"],
    "language_diarization": ["language_diarization_requests", "language_diarization_results"],
}


async def create_service_tables_for_subscriptions(schema_name: str, subscriptions: list[str], db: Optional[AsyncSession] = None):
    """
    Create tables for specific services in a tenant schema.
    
    Args:
        schema_name: The schema name for the tenant
        subscriptions: List of service names to create tables for
        db: Optional AsyncSession to use. If provided, uses existing transaction.
            If None, creates its own session.
    """
    from sqlalchemy import text, MetaData
    from db_connection import TenantDBSessionLocal, ServiceSchemaBase
    from models.service_schema_models import (
        NMTRequestDB, NMTResultDB,
        TTSRequestDB, TTSResultDB,
        ASRRequestDB, ASRResultDB,
        OCRRequestDB, OCRResultDB,
        NERRequestDB, NERResultDB,
        LLMRequestDB, LLMResultDB,
        TransliterationRequestDB, TransliterationResultDB,
        LanguageDetectionRequestDB, LanguageDetectionResultDB,
        SpeakerDiarizationRequestDB, SpeakerDiarizationResultDB,
        AudioLangDetectionRequestDB, AudioLangDetectionResultDB,
        LanguageDiarizationRequestDB, LanguageDiarizationResultDB,
    )
    
    if not subscriptions:
        return
    
    # Get table models for services to create
    tables_to_create = []
    for service in subscriptions:
        service_lower = service.lower()
        if service_lower in SERVICE_TABLE_MAPPING:
            table_names = SERVICE_TABLE_MAPPING[service_lower]
            for table_name in table_names:
                table = ServiceSchemaBase.metadata.tables.get(table_name)
                if table is not None:
                    tables_to_create.append(table)
        else:
            logger.warning(f"Unknown service '{service}' - skipping table creation")
    
    if not tables_to_create:
        return
    
    if db is not None:
        try:
            # Set search_path to tenant schema and fallback to public if needed
            await db.execute(text(f'SET search_path TO "{schema_name}", public'))
            
            # Use a separate MetaData bound to the tenant schema so that tables are
            # physically created under that schema rather than the default 'public'.
            tenant_metadata = MetaData(schema=schema_name)
            
            # Create tables
            # NOTE:
            # - AsyncSession.run_sync passes a synchronous Session, not a raw Connection.
            # - Table.create() needs an Engine/Connection (has _run_ddl_visitor), so we must
            #   call .get_bind() on the sync Session and pass that as the bind.
            # - We clone each table into tenant_metadata with the desired schema name
            #   so that the DDL targets the correct schema.
            for table in tables_to_create:
                await db.run_sync(
                    lambda sync_session, t=table: t.tometadata(tenant_metadata).create(
                        bind=sync_session.get_bind(),
                        checkfirst=True,
                    )
                )
                logger.info(f"Created table '{table.name}' in schema '{schema_name}'")
        finally:
            # Reset search_path
            await db.execute(text('SET search_path TO public'))
    else:
        async with TenantDBSessionLocal() as db:
            try:
                await db.execute(text(f'SET search_path TO "{schema_name}", public'))
            
                tenant_metadata = MetaData(schema=schema_name)
            
                for table in tables_to_create:
                    await db.run_sync(
                        lambda sync_session, t=table: t.tometadata(tenant_metadata).create(
                            bind=sync_session.get_bind(),
                            checkfirst=True,
                        )
                    )
                    logger.info(f"Created table '{table.name}' in schema '{schema_name}'")
                
                await db.commit()
            except Exception as e:
                await db.rollback()
                logger.error(f"Error creating tables for subscriptions {subscriptions} in schema '{schema_name}': {e}")
                raise
            finally:
                await db.execute(text('SET search_path TO public'))


async def drop_service_tables_for_subscriptions(schema_name: str, subscriptions: list[str], db: Optional[AsyncSession] = None):
    """
    Drop tables for specific services in a tenant schema.
    
    Args:
        schema_name: The schema name for the tenant
        subscriptions: List of service names to drop tables for
        db: Optional AsyncSession to use. If provided, uses existing transaction.
            If None, creates its own session.
    """
    from sqlalchemy import text
    from db_connection import TenantDBSessionLocal, ServiceSchemaBase
    from models.service_schema_models import (
        NMTRequestDB, NMTResultDB,
        TTSRequestDB, TTSResultDB,
        ASRRequestDB, ASRResultDB,
        OCRRequestDB, OCRResultDB,
        NERRequestDB, NERResultDB,
        LLMRequestDB, LLMResultDB,
        TransliterationRequestDB, TransliterationResultDB,
        LanguageDetectionRequestDB, LanguageDetectionResultDB,
        SpeakerDiarizationRequestDB, SpeakerDiarizationResultDB,
        AudioLangDetectionRequestDB, AudioLangDetectionResultDB,
        LanguageDiarizationRequestDB, LanguageDiarizationResultDB,
    )
    
    if not subscriptions:
        return
    
    # Get table models for services to remove
    tables_to_drop = []
    for service in subscriptions:
        service_lower = service.lower()
        if service_lower in SERVICE_TABLE_MAPPING:
            table_names = SERVICE_TABLE_MAPPING[service_lower]
            for table_name in table_names:
                table = ServiceSchemaBase.metadata.tables.get(table_name)
                if table is not None:
                    tables_to_drop.append(table)
        else:
            logger.warning(f"Unknown service '{service}' - skipping table drop")
    
    if not tables_to_drop:
        return
    
    if db is not None:
        try:
            # Set search_path to tenant schema and fallback to public if needed
            await db.execute(text(f'SET search_path TO "{schema_name}", public'))
            
            # Drop table with CASCADE to handle foreign key constraints
            for table in tables_to_drop:
                drop_query = text(f'DROP TABLE IF EXISTS "{schema_name}"."{table.name}" CASCADE')
                await db.execute(drop_query)
                logger.info(f"Dropped table '{table.name}' from schema '{schema_name}'")
        finally:
            # Reset search_path
            await db.execute(text('SET search_path TO public'))
    else:
        # Create own session
        async with TenantDBSessionLocal() as db:
            try:
                await db.execute(text(f'SET search_path TO "{schema_name}", public'))
                
                for table in tables_to_drop:
                    drop_query = text(f'DROP TABLE IF EXISTS "{schema_name}"."{table.name}" CASCADE')
                    await db.execute(drop_query)
                    logger.info(f"Dropped table '{table.name}' from schema '{schema_name}'")
                
                await db.commit()
            except Exception as e:
                await db.rollback()
                logger.error(f"Error dropping tables for subscriptions {subscriptions} in schema '{schema_name}': {e}")
                raise
            finally:
                await db.execute(text('SET search_path TO public'))


async def provision_tenant_schema(schema_name: str, subscriptions: list[str]):
    """
    Create tenant-specific PostgreSQL schema and provision service tables based on subscriptions.
    This function is called as a background task after tenant email verification when tenant becomes ACTIVE.
    
    IMPORTANT: This function creates tables ONLY for subscribed services in the tenant schema
    (e.g., 'tenant_acme_corp_5d448a') within the multi_tenant_db database, NOT in the public schema.
    
    Args:
        schema_name: The schema name for the tenant (e.g., 'tenant_acme_corp_5d448a')
        subscriptions: List of service names to create tables for (e.g., ['asr', 'tts'])
    """
    from sqlalchemy import text , MetaData
    from db_connection import TenantDBSessionLocal, ServiceSchemaBase
    # Import all models to ensure they're registered with metadata
    from models.service_schema_models import (
        NMTRequestDB, NMTResultDB,
        TTSRequestDB, TTSResultDB,
        ASRRequestDB, ASRResultDB,
        OCRRequestDB, OCRResultDB,
        NERRequestDB, NERResultDB,
        LLMRequestDB, LLMResultDB,
        TransliterationRequestDB, TransliterationResultDB,
        LanguageDetectionRequestDB, LanguageDetectionResultDB,
        SpeakerDiarizationRequestDB, SpeakerDiarizationResultDB,
        AudioLangDetectionRequestDB, AudioLangDetectionResultDB,
        LanguageDiarizationRequestDB, LanguageDiarizationResultDB,
    )
    
    if not subscriptions:
        logger.warning(f"No subscriptions provided for schema '{schema_name}', skipping table creation")
        return
    
    # Create a new database session for this background task
    async with TenantDBSessionLocal() as db:
        try:
            # Verify we're connected to the correct database
            db_name_query = text("SELECT current_database()")
            result = await db.execute(db_name_query)
            current_db = result.scalar()
            logger.info(f"Connected to database: {current_db}")
            if current_db != DB_NAME:
                logger.warning(f"WARNING: Expected '{DB_NAME}' but connected to '{current_db}'")
            
            # 2. Create schema if not exists
            await db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
            await db.commit()
            logger.info(f"Schema '{schema_name}' created or already exists in database '{current_db}'")
            
            # Create table list for subscribed services
            tables_to_create = []
            for service in subscriptions:
                service_lower = service.lower()
                if service_lower in SERVICE_TABLE_MAPPING:
                    table_names = SERVICE_TABLE_MAPPING[service_lower]
                    for table_name in table_names:
                        table = ServiceSchemaBase.metadata.tables.get(table_name)
                        if table is not None:
                            tables_to_create.append(table)
                        else:
                            logger.warning(f"Table '{table_name}' not found in metadata for service '{service}'")
                else:
                    logger.warning(f"Unknown service '{service}' - no tables to create")
            
            if not tables_to_create:
                logger.warning(f"No valid tables to create for subscriptions: {subscriptions}")
                return
            
            # Set search_path to tenant schema for table creation and fallback to public if needed
            await db.execute(text(f'SET search_path TO "{schema_name}", public'))

            # Use a separate MetaData bound to the tenant schema so that tables are
            # physically created under that schema rather than the default 'public'.
            tenant_metadata = MetaData(schema=schema_name)

            # 5. Create tables for subscribed services only
            # NOTE:
            # - AsyncSession.run_sync passes a synchronous Session, not a raw Connection.
            # - Table.create() needs an Engine/Connection (has _run_ddl_visitor), so we must
            #   call .get_bind() on the sync Session and pass that as the bind.
            # - We clone each table into tenant_metadata with the desired schema name
            #   so that the DDL targets the correct schema.
            for table in tables_to_create:
                await db.run_sync(
                    lambda sync_session, t=table: t.tometadata(tenant_metadata).create(
                        bind=sync_session.get_bind(),
                        checkfirst=True,
                    )
                )
                logger.info(f"Created table '{table.name}' in schema '{schema_name}'")
            
            await db.commit()
            logger.info(f"Successfully provisioned schema '{schema_name}' with {len(tables_to_create)} tables for services: {subscriptions}")
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to provision schema '{schema_name}': {e}")
            logger.exception(f"Error details for schema provisioning: {e}")
            raise
        finally:
            # Ensure search_path is reset
            await db.execute(text('SET search_path TO public'))


async def list_tenant_schemas(db: AsyncSession) -> list[dict]:
    """
    List all tenant schemas in multi_tenant_db.
    
    Returns:
        List of dictionaries with schema information:
        [
            {
                "schema_name": "tenant_acme_corp_5d448a",
                "table_count": 24,
                "tables": ["nmt_requests", "nmt_results", ...]
            },
            ...
        ]
    """
    from sqlalchemy import text
    
    try:
        # 1. Verify we're in the correct database
        db_name_query = text("SELECT current_database()")
        result = await db.execute(db_name_query)
        current_db = result.scalar()
        
        if current_db != "multi_tenant_db":
            logger.warning(f"⚠ WARNING: Expected 'multi_tenant_db' but connected to '{current_db}'")
        
        # 2. Get all schemas that start with 'tenant_' (tenant schemas)
        schemas_query = text("""
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name LIKE 'tenant_%'
            AND catalog_name = current_database()
            ORDER BY schema_name
        """)
        result = await db.execute(schemas_query)
        schema_names = [row[0] for row in result.fetchall()]
        
        # 3. For each schema, get table count and list
        schemas_info = []
        for schema_name in schema_names:
            tables_query = text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = :schema_name
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """)
            result = await db.execute(tables_query, {"schema_name": schema_name})
            tables = [row[0] for row in result.fetchall()]
            
            schemas_info.append({
                "schema_name": schema_name,
                "database": current_db,
                "table_count": len(tables),
                "tables": tables
            })
        
        logger.info(f"Found {len(schemas_info)} tenant schemas in database '{current_db}'")
        return schemas_info
        
    except Exception as e:
        logger.error(f"Error listing tenant schemas: {e}")
        logger.exception(f"Error details: {e}")
        raise


async def verify_tenant_schema(schema_name: str, db: AsyncSession) -> dict:
    """
    Verify a specific tenant schema exists in multi_tenant_db and has all required tables.
    
    Args:
        schema_name: The schema name to verify (e.g., 'tenant_acme_corp_5d448a')
        db: Database session
        
    Returns:
        Dictionary with verification results:
        {
            "schema_name": "tenant_acme_corp_5d448a",
            "database": "multi_tenant_db",
            "exists": True,
            "table_count": 24,
            "expected_tables": [...],
            "missing_tables": [...],
            "tables": [...]
        }
    """
    from sqlalchemy import text
    from db_connection import ServiceSchemaBase
    from models.service_schema_models import (
        NMTRequestDB, NMTResultDB,  # Import to register with metadata
    )
    
    try:
        # 1. Get current database
        db_name_query = text("SELECT current_database()")
        result = await db.execute(db_name_query)
        current_db = result.scalar()
        
        # 2. Check if schema exists
        schema_check = text("""
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name = :schema_name
            AND catalog_name = current_database()
        """)
        result = await db.execute(schema_check, {"schema_name": schema_name})
        schema_exists = result.scalar() is not None
        
        if not schema_exists:
            return {
                "schema_name": schema_name,
                "database": current_db,
                "exists": False,
                "error": f"Schema '{schema_name}' not found in database '{current_db}'"
            }
        
        # 3. Get expected tables from metadata
        expected_tables = list(ServiceSchemaBase.metadata.tables.keys())
        
        # 4. Get actual tables in schema
        tables_query = text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = :schema_name
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        result = await db.execute(tables_query, {"schema_name": schema_name})
        actual_tables = [row[0] for row in result.fetchall()]
        
        # 5. Compare
        missing_tables = set(expected_tables) - set(actual_tables)
        
        return {
            "schema_name": schema_name,
            "database": current_db,
            "exists": True,
            "table_count": len(actual_tables),
            "expected_table_count": len(expected_tables),
            "expected_tables": expected_tables,
            "actual_tables": actual_tables,
            "missing_tables": list(missing_tables),
            "is_complete": len(missing_tables) == 0
        }
        
    except Exception as e:
        logger.error(f"Error verifying tenant schema '{schema_name}': {e}")
        logger.exception(f"Error details: {e}")
        raise


async def send_verification_link(
        created: Tenant, 
        payload: TenantRegisterRequest, 
        db: AsyncSession, 
        subdomain: str, 
        background_tasks: BackgroundTasks
        ):
    """
    Generate and send email verification link to the tenant's contact email.
    
    Args:
        created: The created Tenant object
        payload: The TenantRegisterRequest payload
        db: Database session
        subdomain: The tenant's subdomain (if applicable)
        background_tasks: BackgroundTasks to send email asynchronously
    """

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
    """
    Create a new tenant with PENDING status and send verification email.
    
    Args:
        payload: Tenant registration request payload
        db: Database session
        background_tasks: BackgroundTasks to send email asynchronously
    
    Returns:
        TenantRegisterResponse with tenant details and verification token
    """

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
            
    if not payload.requested_subscriptions:
        raise HTTPException(
            status_code=400,
            detail="Subscriptions cannot be empty. At least one service must be selected.",
        )

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
        "subscriptions": payload.requested_subscriptions,
        "quotas": payload.requested_quotas or DEFAULT_QUOTAS,
        "status": TenantStatus.PENDING,
        "temp_admin_username": "",                 # Will be set upon email verification
        "temp_admin_password_hash": "",            # Will be set upon email verification
        "user_id": None,                           # Will be set upon email verification
    }

    # Validate services are active
    services = await db.scalars(
        select(ServiceConfig).where(
            ServiceConfig.service_name.in_(tenant_data.get("subscriptions", [])),
            ServiceConfig.is_active.is_(True),
        )
    )
    services = services.all()

    requested_services = {s.value for s in tenant_data.get("subscriptions", [])}

    # Extract service names that are valid & active
    active_service_names = {service.service_name for service in services}
    
    # Find missing or inactive services
    invalid_or_inactive_services = set(requested_services) - set(active_service_names)
    
    if invalid_or_inactive_services:
        raise HTTPException(
            status_code=400,
            detail=f"One or more services are invalid or inactive {list(invalid_or_inactive_services)}",
        )
    
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
    """
    Verify email token, activate tenant, create admin user, and trigger schema provisioning.

    Args:
        token: The email verification token
        tenant_db: Database session for tenant operations
        auth_db: Database session for authentication operations
        background_tasks: BackgroundTasks to send email and provision schema asynchronously
    """

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

    # TODO: Add logging for password generation , Remove once done testing
    logger.debug(f"Password generated for Tenant(uuid):-{tenant.id} | Tenant:- {tenant.tenant_id} | password:- {plain_password}")

    # Store temp credentials on tenant for email / audit purposes
    hashed_password = hash_password(plain_password)

    tenant.temp_admin_username = admin_username
    tenant.temp_admin_password_hash = hashed_password

    # Create tenant admin user in auth-service via /api/v1/auth/register
    try:
        async with httpx.AsyncClient(timeout=API_GATEWAY_TIMEOUT) as client:
            auth_response = await client.post(
                f"{API_GATEWAY_URL}/api/v1/auth/register",
                json={
                    "email": tenant.contact_email,
                    "username": admin_username,
                    "password": plain_password,
                    "confirm_password": plain_password,
                    "full_name": tenant.organization_name,
                    "phone_number": None,
                    "timezone": "UTC",
                    "language": "en",
                    "is_tenant": True,
                },
            )
    except httpx.RequestError as e:
        logger.error(f"Failed to call auth-service for tenant admin registration: {e}")
        raise HTTPException(
            status_code=503,
            detail="Authentication service unavailable while creating tenant admin user",
        )

    if auth_response.status_code != 201:
        logger.error(
            f"Auth-service /api/v1/auth/register failed for tenant {tenant.tenant_id}: "
            f"status={auth_response.status_code}, body={auth_response.text}"
        )
        
        raise HTTPException(
            status_code=auth_response.status_code,
            detail=auth_response.json() if auth_response.headers.get("content-type", "").startswith("application/json") else auth_response.text,
        )

    auth_user = auth_response.json()
    admin_user_id = auth_user.get("id")
    if not admin_user_id:
        logger.error(f"Auth-service did not return user id for tenant admin {tenant.tenant_id}: {auth_user}")
        raise HTTPException(
            status_code=500,
            detail="Authentication service response missing user id for tenant admin",
        )

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

    # Insert user_id from auth-service into tenant
    tenant.user_id = admin_user_id

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
        None,  # use subdomain if required
        admin_username_str,
        password_str,
    )

    background_tasks.add_task(
        provision_tenant_schema,
        tenant.schema_name,
        tenant.subscriptions or [],  # Pass subscriptions to create only relevant tables
    )


async def resend_verification_email(
        tenant_id: UUID,
        db: AsyncSession, 
        background_tasks: BackgroundTasks
        ) -> TenantResendEmailVerificationResponse:
    """
    Resend email verification link to a tenant with PENDING or IN_PROGRESS status.
    
    Args:
        tenant_id: The UUID of the tenant
        db: Database session
        background_tasks: BackgroundTasks to send email asynchronously
    """

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

    verification_link = f"{EMAIL_VERIFICATION_LINK}/email/verify?token={token}"

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
    """
    Create a new service configuration with pricing and unit type.

    Args:
        payload: Service creation request payload
        db: Database session
    Returns:
        ServiceResponse: The created service configuration details
    """

    existing = await db.execute(
        select(ServiceConfig)
        .where(ServiceConfig.service_name == payload.service_name)
    )

    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Service '{payload.service_name.value}' already exists",
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
        logger.error(f"Integrity error while creating service {payload.service_name.value}: {e}")
        await db.rollback()
        raise HTTPException(status_code=409,detail=f"Service creation failed - service '{payload.service_name.value}' or ID {service_id} may already exist")
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
    """
    Update service configuration (pricing, unit type, currency) and return changes made.
    
    Args:
        payload: Service update request payload
        db: Database session

    Returns:
        ServiceUpdateResponse: The updated service configuration details and changes made
    """

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
    """
    List all active services with their configuration details.
    
    Args:
        db: Database session
    Returns:
        ListServicesResponse: List of active services and their details 
    """

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

    Args:
        tenant_id: The tenant identifier
        subscriptions: List of service names to add as subscriptions
        db: Database session
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

    # Create tables for newly added services in tenant schema
    if tenant.status == TenantStatus.ACTIVE and tenant.schema_name:
        try:
            await create_service_tables_for_subscriptions(
                schema_name=tenant.schema_name,
                subscriptions=subscriptions,
                db=db,  # Pass existing session to use same transaction
            )
            logger.info(f"Created tables for new subscriptions {subscriptions} in schema '{tenant.schema_name}'")
        except Exception as e:
            logger.error(f"Failed to create tables for new subscriptions {subscriptions}: {e}")
            logger.exception(f"Error details: {e}")
            raise
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
    """
    Remove subscriptions from a tenant and drop corresponding tables from tenant schema.
    
    Args:
        tenant_id: The tenant identifier
        subscriptions: List of service names to remove as subscriptions
        db: Database session
    """

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

    # Drop tables for removed services in tenant schema
    if tenant.status == TenantStatus.ACTIVE and tenant.schema_name:
        try:
            await drop_service_tables_for_subscriptions(
                schema_name=tenant.schema_name,
                subscriptions=subscriptions,
                db=db,  # Pass existing session to use same transaction
            )
            logger.info(f"Dropped tables for removed subscriptions {subscriptions} in schema '{tenant.schema_name}'")
        except Exception as e:
            logger.error(f"Failed to drop tables for removed subscriptions {subscriptions}: {e}")
            logger.exception(f"Error details: {e}")
            raise

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
    Register a user under a tenant, create auth account, billing records, and send welcome email.
    
    Args:
        payload: User registration request payload
        tenant_db: Database session for tenant operations
        auth_db: Database session for authentication operations
        background_tasks: BackgroundTasks to send email asynchronously
    Returns:
        UserRegisterResponse: Details of the registered user
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
        raise HTTPException(
            status_code=400,
            detail="No active services found for user"
        )
    
    if not requested_services:
        raise HTTPException(status_code=400, detail="At least one service is required")
    
    inactive_services = set(requested_services) - tenant_services
    if not requested_services.issubset(tenant_services):
        raise HTTPException(
            status_code=400,
            detail=f"One or more services are not enabled for this tenant {inactive_services}",
        )

    # Validate services are active TODO:
    services = await tenant_db.scalars(
        select(ServiceConfig).where(
            ServiceConfig.service_name.in_(requested_services),
            ServiceConfig.is_active.is_(True),
        )
    )
    services = services.all()

    active_service_names = {service.service_name for service in services}
    
    # Find missing or inactive services
    invalid_or_inactive_services = set(requested_services) - set(active_service_names)
    
    if invalid_or_inactive_services:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "One or more services are invalid or inactive",
                "invalid_services": list(invalid_or_inactive_services),
            },
        )
    
    # Check if user already exists under this tenant
    existing_tenant_user = await tenant_db.scalar(
    select(TenantUser).where(TenantUser.email == payload.email))

    if existing_tenant_user:
        raise HTTPException(status_code=409,detail="User already registered under this tenant")

    # Generate password (if not provided). Hashing is handled by auth-service.
    plain_password = generate_random_password(length=12)

    # Create user in AUTH-SERVICE via /api/v1/auth/register
    try:
        async with httpx.AsyncClient(timeout=API_GATEWAY_TIMEOUT) as client:
            auth_response = await client.post(
                f"{API_GATEWAY_URL}/api/v1/auth/register",
                json={
                    "email": payload.email,
                    "username": payload.username,
                    "password": plain_password,
                    "confirm_password": plain_password,
                    "full_name": payload.full_name,
                    "phone_number": None,
                    "timezone": "UTC",
                    "language": "en",
                    "is_tenant": False,
                },
            )
    except httpx.RequestError as e:
        logger.error(f"Failed to call auth-service for tenant user registration: {e}")
        raise HTTPException(
            status_code=503,
            detail="Authentication service unavailable while creating tenant user",
        )

    if auth_response.status_code != 201:
        logger.error(
            f"Auth-service /api/v1/auth/register failed for tenant user {payload.username} "
            f"under tenant {tenant.tenant_id}: status={auth_response.status_code}, body={auth_response.text}"
        )
        raise HTTPException(
            status_code=auth_response.status_code,
            detail=auth_response.json() if auth_response.headers.get("content-type", "").startswith("application/json") else auth_response.text,
        )

    auth_user = auth_response.json()
    user_id = auth_user.get("id")
    if not user_id:
        logger.error(f"Auth-service did not return user id for tenant user {payload.username}: {auth_user}")
        raise HTTPException(
            status_code=500,
            detail="Authentication service response missing user id for tenant user",
        )
    
    # TODO: Add logging for password generation , Remove once done testing
    logger.debug(f"Password generated for Userid:-{user_id} | Tenant:- {tenant.tenant_id} | password:- {plain_password}")
    
    if payload.is_approved:
        #Create TenantUser entry only if user is approved
        tenant_user = TenantUser(
                user_id=user_id,
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

    # Create UserBillingRecord entries (TENANT DB)
    billing_month = date.today().replace(day=1)

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
        user_id,
        payload.email,
        None,  # add subdomain if required
        payload.username,
        plain_password,
    )

    logger.info(
        f"User registered successfully | tenant={tenant.tenant_id} | user={payload.username}"
    )

    response = UserRegisterResponse(
        user_id=user_id,
        tenant_id=tenant.tenant_id,
        username=payload.username,
        email=payload.email,
        services=list(requested_services),
        schema=tenant.schema_name,
        created_at=datetime.utcnow(),
    )

    return response


async def update_tenant_status(payload: TenantStatusUpdateRequest, db: AsyncSession) -> TenantStatusUpdateResponse:
    """
    Update tenant status and cascade status changes to tenant users and billing records.
    
    Args:
        payload: Tenant status update request payload
        db: Database session
    Returns: 
        TenantStatusUpdateResponse: Details of the updated tenant status
    """

    tenant = await db.scalar(select(Tenant).where(Tenant.tenant_id == payload.tenant_id))

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    old_status = tenant.status
    new_status = payload.status

    if old_status == new_status:
        raise HTTPException(
            status_code=400,
            detail=f"Tenant already in {new_status.value} state",
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



async def update_tenant_user_status(payload: TenantUserStatusUpdateRequest, db: AsyncSession) -> TenantUserStatusUpdateResponse:
    """
    Update a tenant user's status and cascade status changes to their billing records.
    
    Args:
        payload: Tenant user status update request payload
        db: Database session
    Returns:
        TenantUserStatusUpdateResponse: Details of the updated tenant user status
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
            detail=f"User already {payload.status.value}",
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


async def view_tenant_details(tenant_id: str, db: AsyncSession) -> TenantViewResponse:
    """
    View tenant details by tenant_id (human-readable tenant identifier).
    
    Args:
        tenant_id: The tenant identifier
        db: Database session
    Returns:
        TenantViewResponse: Details of the tenant
    """

    tenant = await db.scalar(select(Tenant).where(Tenant.tenant_id == tenant_id))

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    response = TenantViewResponse(
        id=tenant.id,
        tenant_id=tenant.tenant_id,
        user_id=tenant.user_id,
        organization_name=tenant.organization_name,
        email=tenant.contact_email,
        domain=tenant.domain,
        schema=tenant.schema_name,
        subscriptions=tenant.subscriptions or [],
        status=tenant.status,
        quotas=tenant.quotas or {},
        created_at=tenant.created_at.isoformat(),
        updated_at=tenant.updated_at.isoformat(),
    )

    return response


async def view_tenant_user_details(user_id: str, db: AsyncSession) -> TenantUserViewResponse:
    """
    View tenant user details by tenant_id and user_id.
    
    Args:
        tenant_id: The tenant identifier
        user_id: The user identifier
        db: Database session
    Returns:
        TenantUserViewResponse: Details of the tenant user
    """
    tenant_user = await db.scalar(select(TenantUser).where(TenantUser.user_id == user_id))

    if not tenant_user:
        raise HTTPException(status_code=404, detail="Tenant user not found")

    response = TenantUserViewResponse(
        id=tenant_user.id,
        tenant_id=tenant_user.tenant_id,
        user_id=tenant_user.user_id,
        username=tenant_user.username,
        email=tenant_user.email,
        subscriptions=tenant_user.subscriptions or [],
        status=tenant_user.status,
        is_approved=tenant_user.is_approved,
        created_at=tenant_user.created_at.isoformat(),
        updated_at=tenant_user.updated_at.isoformat(),
    )

    return response

async def update_billing_plan(db: AsyncSession,payload: BillingUpdateRequest) -> BillingUpdateResponse:
    """
    Update tenant billing plan and set billing status to PENDING.
    
    Args:
        db: Database session
        payload: Billing update request payload
    Returns:
        BillingUpdateResponse: Details of the updated billing plan
    """

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

