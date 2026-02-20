from fastapi import BackgroundTasks, HTTPException
from datetime import datetime, timezone , timedelta , date

from typing import Optional, List
from sqlalchemy import insert , select , update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError , NoResultFound

import os
import httpx
from pydantic import BaseModel, EmailStr

from utils.utils import (
    generate_tenant_id,
    generate_subdomain,
    schema_name_from_tenant_id,
    now_utc,
    generate_billing_customer_id,
    generate_email_verification_token,
    generate_service_id,
    generate_random_password,
    hash_password,
    encrypt_sensitive_data,
    decrypt_sensitive_data,
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
from models.enum_tenant import  SubscriptionType, TenantStatus, AuditAction , BillingStatus , AuditActorType , TenantUserStatus
from models.tenant_create import TenantRegisterRequest, TenantRegisterResponse
from models.service_create import ServiceCreateRequest , ServiceResponse , ListServicesResponse
from models.user_create import UserRegisterRequest, UserRegisterResponse
from models.services_update import ServiceUpdateRequest , FieldChange , ServiceUpdateResponse
from models.billing_update import BillingUpdateRequest, BillingUpdateResponse
from models.tenant_email import TenantSendEmailVerificationResponse,TenantResendEmailVerificationResponse
from models.tenant_subscription import TenantSubscriptionResponse
from models.tenant_status import TenantStatusUpdateRequest , TenantStatusUpdateResponse
from models.user_status import TenantUserStatusUpdateRequest , TenantUserStatusUpdateResponse
from models.tenant_view import TenantViewResponse, ListTenantsResponse
from models.user_view import TenantUserViewResponse, ListUsersResponse
from models.user_subscription import UserSubscriptionResponse
from models.tenant_update import TenantUpdateRequest, TenantUpdateResponse
from models.user_update import TenantUserUpdateRequest, TenantUserUpdateResponse
from models.user_delete import TenantUserDeleteRequest,TenantUserDeleteResponse

from services.email_service import send_welcome_email, send_verification_email , send_user_welcome_email

from logger import logger
from uuid import UUID
from dotenv import load_dotenv

load_dotenv()

DEFAULT_QUOTAS = {
    "api_calls_per_day": 10_000,
    "storage_gb": 10,
}



EMAIL_VERIFICATION_LINK = str(os.getenv("EMAIL_VERIFICATION_LINK",""))
DB_NAME                 = str(os.getenv("APP_DB_NAME", "multi_tenant_db"))
API_GATEWAY_URL        = str(os.getenv("API_GATEWAY_URL", "http://api-gateway-service:8080"))
API_GATEWAY_TIMEOUT       = float(os.getenv("API_GATEWAY_TIMEOUT", "10"))

# Status transition rules
TENANT_STATUS_TRANSITIONS = {
    TenantStatus.PENDING: [TenantStatus.ACTIVE, TenantStatus.SUSPENDED, TenantStatus.DEACTIVATED],
    TenantStatus.ACTIVE: [TenantStatus.SUSPENDED, TenantStatus.DEACTIVATED],
    TenantStatus.SUSPENDED: [TenantStatus.ACTIVE, TenantStatus.DEACTIVATED],
    TenantStatus.DEACTIVATED: [],  # No transitions allowed from DEACTIVATED
    TenantStatus.IN_PROGRESS: [TenantStatus.ACTIVE, TenantStatus.SUSPENDED, TenantStatus.DEACTIVATED],
}

TENANT_USER_STATUS_TRANSITIONS = {
    TenantUserStatus.ACTIVE: [TenantUserStatus.SUSPENDED, TenantUserStatus.DEACTIVATED],
    TenantUserStatus.SUSPENDED: [TenantUserStatus.ACTIVE, TenantUserStatus.DEACTIVATED],
    TenantUserStatus.DEACTIVATED: [],  # No transitions allowed from DEACTIVATED
}

def validate_status_transition(old_status, new_status, allowed_transitions: dict, entity_type: str = "Entity"):
    """
    Validate if a status transition is allowed.
    
    Args:
        old_status: Current status (TenantStatus or TenantUserStatus)
        new_status: Desired new status (TenantStatus or TenantUserStatus)
        allowed_transitions: Dictionary mapping old status to list of allowed new statuses
        entity_type: Type of entity for error messages (e.g., "Tenant" or "User")
    
    Raises:
        HTTPException: If transition is not allowed
    """
    if old_status not in allowed_transitions:
        raise HTTPException(
            status_code=400,
            detail=f"{entity_type} status {old_status.value} is not configured for status transitions"
        )
    
    # Check if DEACTIVATED status cannot be changed
    if not allowed_transitions[old_status]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot update {entity_type.lower()} status from {old_status.value}. Deactivated entities cannot be modified."
        )
    
    # Check if the desired transition is allowed
    if new_status not in allowed_transitions[old_status]:
        allowed = [s.value for s in allowed_transitions[old_status]]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {entity_type.lower()} status transition from {old_status.value} to {new_status.value}. Allowed transitions: {allowed}"
        )


async def _get_roles_from_auth(user_id: int, auth_header: Optional[str]) -> List[str]:
    """Fetch role names for a user from auth service. Returns empty list on failure or if no header.

    Auth now exposes a single role per user but may return either:
    - {"role": "USER"}
    - {"roles": ["USER"]}
    This helper normalizes that into a list with at most one element.
    """
    if not auth_header:
        return []
    try:
        async with httpx.AsyncClient(timeout=API_GATEWAY_TIMEOUT) as client:
            r = await client.get(
                f"{API_GATEWAY_URL}/api/v1/auth/roles/user/{user_id}",
                headers={"Authorization": auth_header},
            )
            if r.status_code == 200:
                data = r.json()
                # Prefer single role field if present
                if isinstance(data.get("role"), str):
                    role = data["role"].strip()
                    return [role] if role else []
                roles = data.get("roles") or []
                if isinstance(roles, list):
                    return [str(x).strip() for x in roles if str(x).strip()]
                return []
            logger.warning(f"Auth roles/user/{user_id} returned {r.status_code}: {r.text}")
            return []
    except Exception as e:
        logger.warning(f"Failed to fetch roles from auth for user_id={user_id}: {e}")
        return []


async def _assign_role_in_auth(user_id: int, role_name: str, auth_header: Optional[str]) -> bool:
    """Assign a single role to user in auth service (auth allows one role per user). Returns True on success."""
    if not auth_header or not role_name:
        return False
    try:
        async with httpx.AsyncClient(timeout=API_GATEWAY_TIMEOUT) as client:
            r = await client.post(
                f"{API_GATEWAY_URL}/api/v1/auth/roles/assign",
                json={"user_id": user_id, "role_name": role_name},
                headers={"Authorization": auth_header},
            )
            if r.status_code in (200, 201):
                return True
            logger.warning(f"Auth roles/assign for user_id={user_id} role={role_name} returned {r.status_code}: {r.text}")
            return False
    except Exception as e:
        logger.warning(f"Failed to assign role in auth for user_id={user_id} role={role_name}: {e}")
        return False


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

def normalize_to_strings(values):
    """
    Normalize a collection of values to strings.
    Handles enum objects by extracting their .value attribute.
    """
    return [str(v.value) if hasattr(v, 'value') else str(v) for v in values]

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

    verification_link = f"{EMAIL_VERIFICATION_LINK}/api/v1/multi-tenant/email/verify?token={token}"

    background_tasks.add_task(
        send_verification_email,
        payload.contact_email,
        verification_link,
        tenant_id=created.tenant_id,  # Pass tenant_id for resend reference
    )
    return token


async def create_new_tenant(
        payload: TenantRegisterRequest,
        db: AsyncSession,
        background_tasks: BackgroundTasks
        ) -> TenantRegisterResponse:
    """
    Create a new tenant with PENDING status.
    
    Args:
        payload: Tenant registration request payload
        db: Database session
        background_tasks: BackgroundTasks to send email asynchronously
    
    Returns:
        TenantRegisterResponse with tenant details. Verification email is sent via a separate API.
    """

    if payload.contact_email:
        # Check for existing tenant by decrypting stored emails
        # Note: This is not efficient for large datasets. Consider adding email_hash column for searching.
        all_tenants = await db.scalars(select(Tenant).where(Tenant.domain == payload.domain))
        existing = None
        for tenant in all_tenants:
            try:
                decrypted_email = decrypt_sensitive_data(tenant.contact_email)
                if decrypted_email == payload.contact_email:
                    existing = tenant
                    break
            except Exception:
                # If decryption fails, compare directly (backward compatibility)
                if tenant.contact_email == payload.contact_email:
                    existing = tenant
                    break
        
        if existing:
            # Check status
            if existing.status == TenantStatus.PENDING:
                # Tenant already exists and is pending verification.
                # Do NOT automatically resend verification email here to avoid confusion.
                raise ValueError("Tenant registration already pending email verification")
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
    
    # Convert requested_quotas from QuotaStructure to dict, or use DEFAULT_QUOTAS
    quotas_dict = {}
    if payload.requested_quotas:
        quotas_dict = payload.requested_quotas.model_dump(exclude_none=True)
        quotas_dict = {**quotas_dict}
    
    # Convert usage_quota from QuotaStructure to dict, or use empty dict
    usage_dict = {}
    if payload.usage_quota:
        usage_dict = payload.usage_quota.model_dump(exclude_none=True)
    
    # Convert SubscriptionType enums to strings for storage
    subscription_strings = [s.value if hasattr(s, "value") else str(s) for s in payload.requested_subscriptions]
    
    # Encrypt sensitive data before saving
    encrypted_email = encrypt_sensitive_data(payload.contact_email) if payload.contact_email else None
    encrypted_phone = encrypt_sensitive_data(payload.phone_number) if payload.phone_number else None
    
    tenant_data = {
        "tenant_id": tenant_id,
        "organization_name": payload.organization_name,
        "contact_email": encrypted_email,
        "phone_number": encrypted_phone,
        "domain": payload.domain,
        # "subdomain": subdomain,
        "schema_name": schema_name,
        "subscriptions": subscription_strings,
        "quotas": quotas_dict,
        "usage": usage_dict,
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

    requested_services = {s for s in tenant_data.get("subscriptions", [])}

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
            "subscriptions": subscription_strings,
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

    role_value = (getattr(payload, "role", None) or "").strip().upper() or "ADMIN"

    resposne = TenantRegisterResponse(
        id=created.id,
        tenant_id=created.tenant_id,
        schema_name=created.schema_name,
        subscriptions=created.subscriptions or [],
        quotas=created.quotas or {},
        usage_quota=created.usage or {},
        status=created.status.value if hasattr(created.status, "value") else str(created.status),
        role=role_value if role_value in {"ADMIN", "USER", "GUEST", "MODERATOR"} else "ADMIN",
    )

    return resposne


async def send_initial_verification_email(
    tenant_id: str,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> TenantSendEmailVerificationResponse:
    """
    Generate and send the initial email verification link for a tenant.

    This is intended for the first-time send after registration.
    """
    tenant = await db.scalar(select(Tenant).where(Tenant.tenant_id == tenant_id))

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if tenant.status != TenantStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Verification link can only be sent when tenant status is PENDING",
        )

    # Decrypt email before using it
    decrypted_email = decrypt_sensitive_data(tenant.contact_email) if tenant.contact_email else None
    if not decrypted_email:
        raise HTTPException(status_code=400, detail="Tenant email not found or invalid")
    
    # Construct a minimal payload-like object for email helper
    class _Payload(BaseModel):
        contact_email: EmailStr

    payload = _Payload(contact_email=decrypted_email)

    # Reuse the existing token creation + email send helper
    token = await send_verification_link(
        created=tenant,
        payload=payload,  # only contact_email is used
        db=db,
        subdomain=None,
        background_tasks=background_tasks,
    )

    return TenantSendEmailVerificationResponse(
        tenant_uuid=tenant.id,
        tenant_id=tenant.tenant_id,
        token=token,
        message="Verification email sent successfully",
    )


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
    logger.info(f"Password generated for Tenant(uuid):-{tenant.id} | Tenant:- {tenant.tenant_id} | password:- {plain_password}")

    # Store temp credentials on tenant for email / audit purposes
    hashed_password = hash_password(plain_password)

    tenant.temp_admin_username = admin_username
    tenant.temp_admin_password_hash = hashed_password

    # Create tenant admin user in auth-service via /api/v1/auth/register
    try:
        async with httpx.AsyncClient(timeout=API_GATEWAY_TIMEOUT) as client:
            # Decrypt email and phone_number before sending to auth service
            decrypted_email = decrypt_sensitive_data(tenant.contact_email) if tenant.contact_email else None
            decrypted_phone = decrypt_sensitive_data(tenant.phone_number) if tenant.phone_number else None
            
            if not decrypted_email:
                raise HTTPException(status_code=400, detail="Tenant email not found or invalid")
            
            auth_response = await client.post(
                f"{API_GATEWAY_URL}/api/v1/auth/register",
                json={
                    "email": decrypted_email,
                    "username": admin_username,
                    "password": plain_password,
                    "confirm_password": plain_password,
                    "full_name": tenant.organization_name,
                    "phone_number": decrypted_phone,
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
    # Decrypt email before using it
    decrypted_email = decrypt_sensitive_data(tenant.contact_email) if tenant.contact_email else None
    if not decrypted_email:
        raise HTTPException(status_code=400, detail="Tenant email not found or invalid")
    
    tenant_id_str = str(tenant.tenant_id)
    contact_email_str = decrypted_email
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
        tenant_id: str,
        db: AsyncSession, 
        background_tasks: BackgroundTasks
        ) -> TenantResendEmailVerificationResponse:
    """
    Resend email verification link to a tenant with PENDING status.
    
    Args:
        tenant_id: The tenant identifier string (e.g., 'acme-corp')
        db: Database session
        background_tasks: BackgroundTasks to send email asynchronously
    """

    # Look up tenant by string tenant_id
    result = await db.execute(
        select(Tenant).where(Tenant.tenant_id == tenant_id)
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise ValueError(f"Tenant not found with ID: {tenant_id}")

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

    verification_link = f"{EMAIL_VERIFICATION_LINK}/api/v1/multi-tenant/email/verify?token={token}"
   
    # Extract values before adding background task to avoid detached object issues
    # Decrypt email before using it
    decrypted_email = decrypt_sensitive_data(tenant.contact_email) if tenant.contact_email else None
    if not decrypted_email:
        raise HTTPException(status_code=400, detail="Tenant email not found or invalid")
    
    contact_email_str = decrypted_email
    tenant_id_str = str(tenant.tenant_id)

    background_tasks.add_task(
        send_verification_email,
        contact_email_str,
        verification_link,
        tenant_id=tenant_id_str,  # Pass tenant_id for resend reference
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
        raise HTTPException(status_code=400, detail="Tenant is not active , cannot add subscriptions")

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
            detail=f"Invalid subscriptions: {normalize_to_strings(invalid)}",
        )

    current = set(tenant.subscriptions or [])
    duplicates = current & set(subscriptions)

    if duplicates:
        raise HTTPException(
            status_code=400,
            detail=f"Subscription(s) already exist: {normalize_to_strings(duplicates)}",
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
    
    if tenant.status != TenantStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Tenant is not active , cannot remove subscriptions")

    current = set(tenant.subscriptions or [])
    to_remove = set(subscriptions)

    # Validate: subscriptions must exist
    missing = to_remove - current
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Subscriptions not present for tenant: {normalize_to_strings(missing)}",
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
    auth_header: Optional[str] = None,
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
    # Decrypt stored emails to compare (Note: Consider adding email_hash for efficient searching)
    tenant_users = await tenant_db.scalars(
        select(TenantUser).where(TenantUser.tenant_id == tenant.tenant_id)
    )
    existing_tenant_user = None
    for tu in tenant_users:
        try:
            decrypted_email = decrypt_sensitive_data(tu.email)
            if decrypted_email == payload.email:
                existing_tenant_user = tu
                break
        except Exception:
            # If decryption fails, compare directly (backward compatibility)
            if tu.email == payload.email:
                existing_tenant_user = tu
                break

    if existing_tenant_user:
        raise HTTPException(status_code=409,detail="Email already registered , please use a different email")
    

    if not payload.is_approved:
        raise HTTPException(status_code=400, detail="User must be approved by tenant admin to register")

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
                    "phone_number": payload.phone_number,
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

    # Assign role in auth service (one role per user). Auth register already sets USER by default.
    # Role is validated by UserRegisterRequest (ADMIN, USER, GUEST, MODERATOR)
    role_name = (payload.role or "").strip().upper() if getattr(payload, "role", None) else ""
    if role_name and auth_header:
        assigned = await _assign_role_in_auth(user_id, role_name, auth_header)
        if not assigned:
            logger.warning(f"Could not assign role {role_name} to user_id={user_id}; auth may use default.")
    
    # TODO: Add logging for password generation , Remove once done testing
    logger.info(f"Password generated for Userid:-{user_id} | Tenant:- {tenant.tenant_id} | password:- {plain_password}")
    
    if payload.is_approved:
        #Create TenantUser entry only if user is approved
        # Encrypt sensitive data before saving
        encrypted_user_email = encrypt_sensitive_data(payload.email) if payload.email else None
        encrypted_user_phone = encrypt_sensitive_data(payload.phone_number) if payload.phone_number else None
        
        tenant_user = TenantUser(
                user_id=user_id,
                tenant_uuid=tenant.id,
                tenant_id=tenant.tenant_id,
                username=payload.username,
                email=encrypted_user_email,
                phone_number=encrypted_user_phone,
                subscriptions=list(requested_services),
                status=TenantUserStatus.ACTIVE, 
                is_approved=True,
        )

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

    # Determine final role for response: prefer value from auth, fallback to requested or USER
    auth_roles = await _get_roles_from_auth(user_id, auth_header)
    final_role = auth_roles[0] if auth_roles else (role_name or "USER")

    response = UserRegisterResponse(
        user_id=user_id,
        tenant_id=tenant.tenant_id,
        username=payload.username,
        email=payload.email,
        services=list(requested_services),
        schema=tenant.schema_name,
        created_at=datetime.utcnow(),
        role=final_role,
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

    # Validate status transition rules
    validate_status_transition(old_status, new_status, TENANT_STATUS_TRANSITIONS, "Tenant")

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
    elif new_status == TenantStatus.DEACTIVATED:
        await db.execute(
            update(TenantUser)
            .where(TenantUser.tenant_id == payload.tenant_id)
            .values(status=TenantUserStatus.DEACTIVATED)
        )
        # Deactivate user billing records
        await db.execute(
            update(UserBillingRecord)
            .where(UserBillingRecord.tenant_id == payload.tenant_id)
            .values(status=TenantUserStatus.DEACTIVATED)
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

        elif new_status == TenantStatus.DEACTIVATED:
            billing_record.billing_status = BillingStatus.DEACTIVATED
            billing_record.suspension_reason = payload.reason if payload.reason else ""
            billing_record.suspended_until = None
    
    action = None

    if new_status == TenantStatus.SUSPENDED:
        action = AuditAction.tenant_suspended

     # Tenant is made active during the registration process
     # so if the tenant status is changed to ACTIVE through this api it is considered a reactivation
    elif new_status == TenantStatus.ACTIVE: 
        action = AuditAction.tenant_reactivated

    elif new_status == TenantStatus.DEACTIVATED:
        action = AuditAction.tenant_deactivated

    # Audit log for tenant status change
    db.add(
        AuditLog(
            tenant_id=tenant.id,
            action=action,
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

    if tenant.status == TenantStatus.SUSPENDED or tenant.status == TenantStatus.DEACTIVATED:
        raise HTTPException(
            status_code=400,
            detail="Cannot update user status while tenant is suspended or deactivated",
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
    
    # Validate status transition rules
    validate_status_transition(old_status, payload.status, TENANT_USER_STATUS_TRANSITIONS, "User")
    
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


async def update_tenant_user(
    payload: TenantUserUpdateRequest,
    db: AsyncSession,
    auth_header: Optional[str] = None,
) -> TenantUserUpdateResponse:
    """
    Update tenant user information (username, email, approval flag, roles).
    Supports partial updates - only provided fields will be updated.
    Roles are updated in auth service by user_id.
    """

    tenant = await db.scalar(select(Tenant).where(Tenant.tenant_id == payload.tenant_id))

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant_user = await db.scalar(
        select(TenantUser).where(
            TenantUser.tenant_id == payload.tenant_id,
            TenantUser.user_id == payload.user_id,
        )
    )

    if tenant_user and tenant_user.status == TenantUserStatus.DEACTIVATED:
        raise HTTPException(status_code=400, detail="Cannot update deactivated tenant user")
    
    if tenant.status == TenantStatus.SUSPENDED or tenant.status == TenantStatus.DEACTIVATED:
        raise HTTPException(
            status_code=400,
            detail="Cannot update tenant user while tenant is suspended",
        )

    if not tenant_user:
        raise HTTPException(status_code=404, detail="Tenant user not found")

    update_data = payload.model_dump(
        exclude_unset=True,
        exclude={"tenant_id", "user_id"},
    )

    if not update_data:
        raise HTTPException(
            status_code=400,
            detail="No fields provided for update",
        )

    changes: dict[str, FieldChange] = {}
    updated_fields: list[str] = []

    # Handle role update (auth service: one role per user)
    # Role is validated by TenantUserUpdateRequest (ADMIN, USER, GUEST, MODERATOR)
    if "role" in update_data:
        new_role = (update_data.pop("role") or "").strip().upper()
        if new_role and auth_header:
            assigned = await _assign_role_in_auth(payload.user_id, new_role, auth_header)
            if assigned:
                updated_fields.append("role")
                changes["role"] = FieldChange(old="(from auth)", new=new_role)

    # Handle username update
    if "username" in update_data:
        old_value = tenant_user.username
        new_value = update_data["username"]
        if old_value != new_value:
            changes["username"] = FieldChange(old=old_value, new=new_value)
            tenant_user.username = new_value
            updated_fields.append("username")

    # Handle email update
    if "email" in update_data:
        old_value = tenant_user.email
        new_value = update_data["email"]
        if old_value != new_value:
            changes["email"] = FieldChange(old=old_value, new=new_value)
            tenant_user.email = new_value
            updated_fields.append("email")

    # Handle is_approved update
    if "is_approved" in update_data:
        old_value = tenant_user.is_approved
        new_value = update_data["is_approved"]
        if old_value != new_value:
            changes["is_approved"] = FieldChange(old=old_value, new=new_value)
            tenant_user.is_approved = new_value
            updated_fields.append("is_approved")

    if not changes:
        raise HTTPException(
            status_code=400,
            detail="No changes detected. All provided values are the same as current values.",
        )

    # Audit log
    audit = AuditLog(
        tenant_id=tenant.id,
        action=AuditAction.user_updated,
        actor=AuditActorType.USER,
        details={
            "user_id": payload.user_id,
            "updated_fields": updated_fields,
            "changes": {
                field: {"old": str(change.old), "new": str(change.new)}
                for field, change in changes.items()
            },
        },
    )
    db.add(audit)

    try:
        await db.commit()
        await db.refresh(tenant_user)
    except IntegrityError as e:
        await db.rollback()
        logger.error(
            f"Integrity error while updating tenant user | tenant={payload.tenant_id} user_id={payload.user_id}: {e}"
        )
        raise HTTPException(
            status_code=409,
            detail="Tenant user update failed due to integrity constraint violation (e.g., email already exists)",
        )
    except Exception as e:
        await db.rollback()
        logger.exception(
            f"Error committing tenant user update to database | tenant={payload.tenant_id} user_id={payload.user_id}: {e}"
        )
        raise HTTPException(status_code=500, detail="Failed to update tenant user")

    logger.info(
        f"Tenant user updated successfully | tenant_id={payload.tenant_id} | "
        f"user_id={payload.user_id} | updated_fields={updated_fields}"
    )

    role_value: Optional[str] = None
    if "role" in updated_fields or auth_header:
        auth_roles = await _get_roles_from_auth(payload.user_id, auth_header)
        role_value = auth_roles[0] if auth_roles else None

    return TenantUserUpdateResponse(
        tenant_id=payload.tenant_id,
        user_id=payload.user_id,
        message=f"Tenant user updated successfully. {len(updated_fields)} field(s) modified.",
        changes=changes,
        updated_fields=updated_fields,
        role=role_value,
    )


async def delete_tenant_user(
    payload: TenantUserDeleteRequest,
    db: AsyncSession,
) -> TenantUserDeleteResponse:
    """
    Delete a tenant user and cascade deletions to related records (e.g., billing).

    Args:
        payload: Tenant user delete request payload
        db: Database session
    Returns:
        TenantUserDeleteResponse: Deletion confirmation
    """

    tenant = await db.scalar(select(Tenant).where(Tenant.tenant_id == payload.tenant_id))

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant_user = await db.scalar(
        select(TenantUser).where(
            TenantUser.tenant_id == payload.tenant_id,
            TenantUser.user_id == payload.user_id,
        )
    )

    if not tenant_user:
        raise HTTPException(status_code=404, detail="Tenant user not found")

    # Delete the tenant user (will cascade to related records via FK constraints)
    await db.delete(tenant_user)

    # Audit log for deletion
    db.add(
        AuditLog(
            tenant_id=tenant.id,
            action=AuditAction.user_deleted,
            actor=AuditActorType.ADMIN,
            details={
                "user_id": payload.user_id,
                "username": tenant_user.username,
                "email": tenant_user.email,
            },
        )
    )

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        logger.error(
            f"Integrity error while deleting tenant user | tenant={payload.tenant_id} user_id={payload.user_id}: {e}"
        )
        raise HTTPException(
            status_code=409,
            detail="Tenant user deletion failed due to integrity constraint violation",
        )
    except Exception as e:
        await db.rollback()
        logger.exception(
            f"Error committing tenant user deletion to database | tenant={payload.tenant_id} user_id={payload.user_id}: {e}"
        )
        raise HTTPException(status_code=500, detail="Failed to delete tenant user")

    logger.info(
        f"Tenant user deleted successfully | tenant_id={payload.tenant_id} | user_id={payload.user_id}"
    )

    return TenantUserDeleteResponse(
        tenant_id=payload.tenant_id,
        user_id=payload.user_id,
        message="Tenant user deleted successfully",
    )


async def view_tenant_details(
    tenant_id: str,
    db: AsyncSession,
    auth_header: Optional[str] = None,
) -> TenantViewResponse:
    """
    View tenant details by tenant_id (human-readable tenant identifier).
    Includes tenant admin role from auth service when auth_header is provided.
    """

    tenant = await db.scalar(select(Tenant).where(Tenant.tenant_id == tenant_id))

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    role = ""
    if tenant.user_id and auth_header:
        auth_roles = await _get_roles_from_auth(tenant.user_id, auth_header)
        role = auth_roles[0] if auth_roles else ""

    # Decrypt sensitive data for display
    decrypted_email = decrypt_sensitive_data(tenant.contact_email) if tenant.contact_email else None
    decrypted_phone = decrypt_sensitive_data(tenant.phone_number) if tenant.phone_number else None
    
    # Validate email - ensure it's a valid email format for Pydantic
    if not decrypted_email:
        decrypted_email = "unknown@example.com"
    elif decrypted_email.startswith('gAAAAA'):
        # Still encrypted - decryption failed
        logger.error(
            f"CRITICAL: Failed to decrypt email for tenant {tenant.tenant_id}. "
            f"This usually means the encryption key changed. "
            f"Encrypted value starts with: {decrypted_email[:20]}..."
        )
        decrypted_email = "encrypted@example.com"
    elif '@' not in decrypted_email:
        # Invalid email format (no @ sign)
        logger.warning(
            f"Invalid email format for tenant {tenant.tenant_id}: {decrypted_email[:20]}..."
        )
        decrypted_email = "invalid@example.com"
    
    response = TenantViewResponse(
        id=tenant.id,
        tenant_id=tenant.tenant_id,
        user_id=tenant.user_id or None,
        organization_name=tenant.organization_name,
        email=decrypted_email,  # Validated above
        phone_number=decrypted_phone,
        domain=tenant.domain,
        schema=tenant.schema_name,
        subscriptions=tenant.subscriptions or [],
        status=tenant.status.value if hasattr(tenant.status, "value") else str(tenant.status),
        quotas=tenant.quotas or {},
        usage_quota=tenant.usage or {},
        created_at=tenant.created_at.isoformat(),
        updated_at=tenant.updated_at.isoformat(),
        role=role,
    )

    return response


async def update_tenant(
    payload: TenantUpdateRequest,
    db: AsyncSession,
    auth_header: Optional[str] = None,
) -> TenantUpdateResponse:
    """
    Update tenant information including quotas, usage_quota, and tenant admin role.
    Supports partial updates - only provided fields will be updated.
    Role is updated in auth service via tenant.user_id.
    """
    tenant = await db.scalar(select(Tenant).where(Tenant.tenant_id == payload.tenant_id))
    
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Get update data excluding unset fields
    update_data = payload.model_dump(exclude_unset=True, exclude={"tenant_id"})
    
    if not update_data:
        raise HTTPException(
            status_code=400,
            detail="No fields provided for update"
        )
    
    changes = {}
    updated_fields = []
    
    # Handle role update (tenant admin's role in auth service)
    if "role" in update_data:
        new_role = (update_data.pop("role") or "").strip().upper()
        if new_role and tenant.user_id and auth_header:
            assigned = await _assign_role_in_auth(tenant.user_id, new_role, auth_header)
            if assigned:
                updated_fields.append("role")
                changes["role"] = FieldChange(old="(from auth)", new=new_role)
    
    # Handle organization_name update
    if "organization_name" in update_data:
        old_value = tenant.organization_name
        new_value = update_data["organization_name"]
        if old_value != new_value:
            changes["organization_name"] = FieldChange(old=old_value, new=new_value)
            tenant.organization_name = new_value
            updated_fields.append("organization_name")
    
    # Handle contact_email update
    if "contact_email" in update_data:
        old_value = tenant.contact_email
        new_value = update_data["contact_email"]
        if old_value != new_value:
            changes["contact_email"] = FieldChange(old=old_value, new=new_value)
            tenant.contact_email = new_value
            updated_fields.append("contact_email")
    
    # Handle domain update
    if "domain" in update_data:
        old_value = tenant.domain
        new_value = update_data["domain"]
        if old_value != new_value:
            changes["domain"] = FieldChange(old=old_value, new=new_value)
            tenant.domain = new_value
            updated_fields.append("domain")
    
    # Handle requested_quotas update
    if "requested_quotas" in update_data:
        old_quotas = tenant.quotas or {}
        quota_structure = update_data["requested_quotas"]
        # Convert QuotaStructure to dict, merge with existing quotas
        new_quotas_dict = quota_structure
        # Merge with existing quotas to preserve other fields
        merged_quotas = {**old_quotas, **new_quotas_dict}
        
        if old_quotas != merged_quotas:
            changes["requested_quotas"] = FieldChange(old=old_quotas, new=merged_quotas)
            tenant.quotas = merged_quotas
            updated_fields.append("requested_quotas")
    
    # Handle usage_quota update
    if "usage_quota" in update_data:
        old_usage = tenant.usage or {}
        usage_structure = update_data["usage_quota"]
        # Convert QuotaStructure to dict, merge with existing usage
        new_usage_dict = usage_structure
        # Merge with existing usage to preserve other fields
        merged_usage = {**old_usage, **new_usage_dict}
        
        if old_usage != merged_usage:
            changes["usage_quota"] = FieldChange(old=old_usage, new=merged_usage)
            tenant.usage = merged_usage
            updated_fields.append("usage_quota")
    
    if not changes:
        raise HTTPException(
            status_code=400,
            detail="No changes detected. All provided values are the same as current values."
        )
    
    # Create audit log
    audit = AuditLog(
        tenant_id=tenant.id,
        action=AuditAction.tenant_updated,
        actor=AuditActorType.USER,
        details={
            "updated_fields": updated_fields,
            "changes": {k: {"old": str(v.old), "new": str(v.new)} for k, v in changes.items()},
        },
    )
    db.add(audit)
    
    try:
        await db.commit()
        await db.refresh(tenant)
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"Integrity error while updating tenant {payload.tenant_id}: {e}")
        raise HTTPException(
            status_code=409,
            detail="Tenant update failed due to integrity constraint violation (e.g., domain already exists)"
        )
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error committing tenant update to database | tenant={payload.tenant_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update tenant")
    
    logger.info(f"Tenant updated successfully | tenant_id={payload.tenant_id} | updated_fields={updated_fields}")

    role_value: Optional[str] = None
    if tenant.user_id and auth_header:
        auth_roles = await _get_roles_from_auth(tenant.user_id, auth_header)
        role_value = auth_roles[0] if auth_roles else None

    return TenantUpdateResponse(
        tenant_id=tenant.tenant_id,
        message=f"Tenant updated successfully. {len(updated_fields)} field(s) modified.",
        changes=changes,
        updated_fields=updated_fields,
        role=role_value,
    )


async def view_tenant_user_details(
    user_id: int,
    db: AsyncSession,
    auth_header: Optional[str] = None,
) -> TenantUserViewResponse:
    """
    View tenant user details by auth user_id. Optionally includes roles from auth service.
    """
    tenant_user = await db.scalar(select(TenantUser).where(TenantUser.user_id == user_id))

    if not tenant_user:
        raise HTTPException(status_code=404, detail="Tenant user not found")

    role_names = await _get_roles_from_auth(tenant_user.user_id, auth_header)
    role = role_names[0] if role_names else ""

    # Decrypt sensitive data for display
    decrypted_email = decrypt_sensitive_data(tenant_user.email) if tenant_user.email else None
    decrypted_phone = decrypt_sensitive_data(tenant_user.phone_number) if tenant_user.phone_number else None
    
    # Validate email - ensure it's a valid email format for Pydantic
    if not decrypted_email:
        decrypted_email = "unknown@example.com"
    elif decrypted_email.startswith('gAAAAA'):
        # Still encrypted - decryption failed
        logger.error(
            f"CRITICAL: Failed to decrypt email for tenant user {tenant_user.user_id}. "
            f"This usually means the encryption key changed. "
            f"Encrypted value starts with: {decrypted_email[:20]}..."
        )
        decrypted_email = "encrypted@example.com"
    elif '@' not in decrypted_email:
        # Invalid email format (no @ sign)
        logger.warning(
            f"Invalid email format for tenant user {tenant_user.user_id}: {decrypted_email[:20]}..."
        )
        decrypted_email = "invalid@example.com"
    
    response = TenantUserViewResponse(
        id=tenant_user.id,
        tenant_id=tenant_user.tenant_id,
        user_id=tenant_user.user_id,
        username=tenant_user.username,
        email=decrypted_email,  # Validated above
        phone_number=decrypted_phone,
        subscriptions=tenant_user.subscriptions or [],
        status=tenant_user.status.value if hasattr(tenant_user.status, "value") else str(tenant_user.status),
        is_approved=tenant_user.is_approved,
        created_at=tenant_user.created_at.isoformat(),
        updated_at=tenant_user.updated_at.isoformat(),
        role=role,
    )

    return response


async def list_all_tenants(
    db: AsyncSession,
    auth_header: Optional[str] = None,
) -> ListTenantsResponse:
    """
    List all tenants with their details.
    Includes tenant admin role from auth service when auth_header is provided.
    """
    result = await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    tenants = result.scalars().all()

    tenant_list = []
    for tenant in tenants:
        role = ""
        if tenant.user_id and auth_header:
            auth_roles = await _get_roles_from_auth(tenant.user_id, auth_header)
            role = auth_roles[0] if auth_roles else ""
        
        # Decrypt sensitive data for display
        decrypted_email = decrypt_sensitive_data(tenant.contact_email) if tenant.contact_email else None
        decrypted_phone = decrypt_sensitive_data(tenant.phone_number) if tenant.phone_number else None
        
        # Validate email - ensure it's a valid email format for Pydantic
        # Check multiple conditions to catch all failure cases
        if not decrypted_email:
            decrypted_email = "unknown@example.com"
        elif decrypted_email.startswith('gAAAAA'):
            # Still encrypted - decryption failed
            logger.error(
                f"CRITICAL: Failed to decrypt email for tenant {tenant.tenant_id}. "
                f"This usually means the encryption key changed. "
                f"Encrypted value starts with: {decrypted_email[:20]}..."
            )
            decrypted_email = "encrypted@example.com"
        elif '@' not in decrypted_email:
            # Invalid email format (no @ sign)
            logger.warning(
                f"Invalid email format for tenant {tenant.tenant_id}: {decrypted_email[:20]}..."
            )
            decrypted_email = "invalid@example.com"
        
        tenant_list.append(
            TenantViewResponse(
                id=tenant.id,
                tenant_id=tenant.tenant_id,
                user_id=tenant.user_id or 0,
                organization_name=tenant.organization_name,
                email=decrypted_email,  # Validated above
                phone_number=decrypted_phone,
                domain=tenant.domain,
                schema=tenant.schema_name,
                subscriptions=tenant.subscriptions or [],
                status=tenant.status.value if hasattr(tenant.status, "value") else str(tenant.status),
                quotas=tenant.quotas or {},
                usage_quota=tenant.usage or {},
                created_at=tenant.created_at.isoformat(),
                updated_at=tenant.updated_at.isoformat(),
                role=role,
            )
        )

    return ListTenantsResponse(
        count=len(tenant_list),
        tenants=tenant_list,
    )


async def list_all_users(
    db: AsyncSession,
    tenant_id: Optional[str] = None,
    auth_header: Optional[str] = None,
) -> ListUsersResponse:
    """
    List tenant users. If tenant_id is provided, only users for that tenant are returned.
    Roles are fetched from auth service when auth_header is provided.
    """
    stmt = select(TenantUser)
    if tenant_id:
        stmt = stmt.where(TenantUser.tenant_id == tenant_id)
    stmt = stmt.order_by(TenantUser.created_at.desc())

    result = await db.execute(stmt)
    users = result.scalars().all()

    user_list = []
    for user in users:
        role_names = await _get_roles_from_auth(user.user_id, auth_header)
        role = role_names[0] if role_names else ""
        
        # Decrypt sensitive data for display
        decrypted_email = decrypt_sensitive_data(user.email) if user.email else None
        decrypted_phone = decrypt_sensitive_data(user.phone_number) if user.phone_number else None
        
        # Validate email - ensure it's a valid email format for Pydantic
        if not decrypted_email:
            decrypted_email = "unknown@example.com"
        elif decrypted_email.startswith('gAAAAA'):
            # Still encrypted - decryption failed
            logger.error(
                f"CRITICAL: Failed to decrypt email for tenant user {user.user_id}. "
                f"This usually means the encryption key changed. "
                f"Encrypted value starts with: {decrypted_email[:20]}..."
            )
            decrypted_email = "encrypted@example.com"
        elif '@' not in decrypted_email:
            # Invalid email format (no @ sign)
            logger.warning(
                f"Invalid email format for tenant user {user.user_id}: {decrypted_email[:20]}..."
            )
            decrypted_email = "invalid@example.com"
        
        user_list.append(
            TenantUserViewResponse(
                id=user.id,
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                username=user.username,
                email=decrypted_email,  # Validated above
                phone_number=decrypted_phone,
                subscriptions=user.subscriptions or [],
                status=user.status.value if hasattr(user.status, "value") else str(user.status),
                is_approved=user.is_approved,
                created_at=user.created_at.isoformat(),
                updated_at=user.updated_at.isoformat(),
                role=role,
            )
        )

    return ListUsersResponse(
        count=len(user_list),
        users=user_list,
    )


async def add_user_subscriptions(
    tenant_id: str,
    user_id: int,
    subscriptions: list[str],
    db: AsyncSession,
) -> UserSubscriptionResponse:
    """
    Add subscriptions to a tenant user.
    Validates tenant, tenant user, and that requested services are enabled and active.
    """

    tenant = await db.scalar(select(Tenant).where(Tenant.tenant_id == tenant_id))

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if tenant.status != TenantStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Tenant is not active , cannot add user subscriptions")

    tenant_user = await db.scalar(
        select(TenantUser).where(
            TenantUser.tenant_id == tenant_id,
            TenantUser.user_id == user_id,
        )
    )

    if not tenant_user:
        raise HTTPException(status_code=404, detail="Tenant user not found")

    # Tenant must have the services enabled
    tenant_services = set(tenant.subscriptions or [])
    requested_services = set(subscriptions)
    missing_for_tenant = requested_services - tenant_services
    if missing_for_tenant:
        raise HTTPException(
            status_code=400,
            detail=f"One or more services are not enabled for this tenant: {normalize_to_strings(missing_for_tenant)}",
        )

    # Validate services are active
    services = await db.scalars(
        select(ServiceConfig).where(
            ServiceConfig.service_name.in_(requested_services),
            ServiceConfig.is_active.is_(True),
        )
    )
    services = services.all()
    active_service_names = {service.service_name for service in services}

    invalid_or_inactive = requested_services - active_service_names
    if invalid_or_inactive:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "One or more services are invalid or inactive",
                "invalid_services": normalize_to_strings(invalid_or_inactive),
            },
        )

    current = set(tenant_user.subscriptions or [])
    duplicates = current & requested_services
    if duplicates:
        raise HTTPException(
            status_code=400,
            detail=f"Subscription(s) already exist for user: {normalize_to_strings(duplicates)}",
        )

    updated = list(current | requested_services)
    tenant_user.subscriptions = updated

    # Audit log for user subscription add
    db.add(
        AuditLog(
            tenant_id=tenant.id,
            action=AuditAction.user_updated,
            actor=AuditActorType.ADMIN,
            details={
                "user_id": user_id,
                "added_subscriptions": list(requested_services),
            },
        )
    )

    try:
        await db.commit()
        await db.refresh(tenant_user)
    except IntegrityError as e:
        logger.error(
            f"Integrity error while adding user subscriptions | tenant={tenant_id} user_id={user_id}: {e}"
        )
        await db.rollback()
        raise HTTPException(status_code=409, detail="Failed to add user subscriptions")
    except Exception as e:
        logger.exception(
            f"Error committing user subscription changes to database | tenant={tenant_id} user_id={user_id}: {e}"
        )
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to add user subscriptions")

    return UserSubscriptionResponse(
        tenant_id=tenant_id,
        user_id=user_id,
        subscriptions=tenant_user.subscriptions or [],
    )


async def remove_user_subscriptions(
    tenant_id: str,
    user_id: int,
    subscriptions: list[str],
    db: AsyncSession,
) -> UserSubscriptionResponse:
    """
    Remove subscriptions from a tenant user.
    Validates that subscriptions exist for the user.
    """

    tenant = await db.scalar(select(Tenant).where(Tenant.tenant_id == tenant_id))

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    if tenant.status != TenantStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Tenant is not active , cannot remove subscriptions")

    tenant_user = await db.scalar(
        select(TenantUser).where(
            TenantUser.tenant_id == tenant_id,
            TenantUser.user_id == user_id,
        )
    )

    if not tenant_user:
        raise HTTPException(status_code=404, detail="Tenant user not found")
    
    current = set(tenant_user.subscriptions or [])
    to_remove = set(subscriptions)

    missing = to_remove - current
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Subscriptions not present for user: {list(missing)}",
        )

    updated = list(current - to_remove)
    tenant_user.subscriptions = updated

    # Audit log for user subscription removal
    db.add(
        AuditLog(
            tenant_id=tenant.id,
            action=AuditAction.user_updated,
            actor=AuditActorType.ADMIN,
            details={
                "user_id": user_id,
                "removed_subscriptions": list(to_remove),
            },
        )
    )

    try:
        await db.commit()
        await db.refresh(tenant_user)
    except IntegrityError as e:
        logger.error(
            f"Integrity error while removing user subscriptions | tenant={tenant_id} user_id={user_id}: {e}"
        )
        await db.rollback()
        raise HTTPException(status_code=409, detail="Failed to remove user subscriptions")
    except Exception as e:
        logger.exception(
            f"Error committing user subscription removal to database | tenant={tenant_id} user_id={user_id}: {e}"
        )
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to remove user subscriptions")

    return UserSubscriptionResponse(
        tenant_id=tenant_id,
        user_id=user_id,
        subscriptions=tenant_user.subscriptions or [],
    )

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

