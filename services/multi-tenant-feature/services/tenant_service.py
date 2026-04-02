from fastapi import BackgroundTasks, HTTPException
from datetime import datetime, timezone , timedelta , date

from typing import Optional, List
from sqlalchemy import insert , select , update , delete , text , MetaData , func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError , NoResultFound

import httpx
from pydantic import BaseModel, EmailStr
from ai4icore_env import app_env

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
    hash_email,
    encrypt_sensitive_data,
    decrypt_sensitive_data,
    DecryptionError,
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
from models.auth_models import Role, UserRole, UserDB

from models.enum_tenant import  (
    SubscriptionType, 
    TenantStatus, 
    AuditAction , 
    BillingStatus , 
    AuditActorType , 
    TenantUserStatus
    )

from models.tenant_create import TenantRegisterRequest, TenantRegisterResponse
from models.tenant_subscription import TenantSubscriptionResponse
from models.tenant_status import TenantStatusUpdateRequest , TenantStatusUpdateResponse
from models.tenant_view import TenantViewResponse, ListTenantsResponse
from models.tenant_update import TenantUpdateRequest, TenantUpdateResponse

from models.service_create import ServiceCreateRequest , ServiceResponse , ListServicesResponse
from models.service_update import ServiceUpdateRequest , FieldChange , ServiceUpdateResponse
from models.service_delete import  ServiceDeleteRequest , ServiceDeleteResponse

from models.user_create import UserRegisterRequest, UserRegisterResponse
from models.user_status import TenantUserStatusUpdateRequest , TenantUserStatusUpdateResponse
from models.user_view import TenantUserViewResponse, ListUsersResponse
from models.user_subscription import UserSubscriptionResponse
from models.user_update import TenantUserUpdateRequest, TenantUserUpdateResponse
from models.user_delete import TenantUserDeleteRequest,TenantUserDeleteResponse

from models.tenant_email import TenantSendEmailVerificationResponse,TenantResendEmailVerificationResponse
from services.email_service import send_welcome_email, send_verification_email , send_user_welcome_email
from models.billing_update import BillingUpdateRequest, BillingUpdateResponse

from logger import logger
from uuid import UUID
from dotenv import load_dotenv

load_dotenv()

DEFAULT_QUOTAS = {
    "api_calls_per_day": 10_000,
    "storage_gb": 10,
}



EMAIL_VERIFICATION_LINK = app_env.email_verification_link
EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES = app_env.email_verification_token_expire_minutes
EMAIL_VERIFICATION_RESEND_MIN_INTERVAL_SECONDS = app_env.email_verification_resend_min_interval_seconds
EMAIL_VERIFICATION_RESEND_MAX_PER_HOUR = app_env.email_verification_resend_max_per_hour
EMAIL_VERIFICATION_RESEND_MAX_PER_DAY = app_env.email_verification_resend_max_per_day
DB_NAME                 = str(app_env.app_db_name)
API_GATEWAY_URL        = app_env.api_gateway_url
API_GATEWAY_TIMEOUT       = app_env.api_gateway_timeout


async def invalidate_pending_verification_tokens(
    tenant_id,
    db: AsyncSession,
    *,
    invalidated_at: Optional[datetime] = None,
):
    """
    Expire every unverified token for a tenant so that only a newly issued one can be used.
    """
    invalidated_at = invalidated_at or now_utc()

    await db.execute(
        update(TenantEmailVerification)
        .where(
            TenantEmailVerification.tenant_id == tenant_id,
            TenantEmailVerification.verified_at.is_(None),
            TenantEmailVerification.expires_at >= invalidated_at,
        )
        .values(expires_at=invalidated_at - timedelta(seconds=1))
    )


async def _count_verification_resends_since(
    tenant_uuid,
    db: AsyncSession,
    *,
    since: datetime,
) -> int:
    """
    Count resend attempts since the provided timestamp.

    The first-ever verification email is treated as the initial send.
    Every later verification token issued for the tenant is treated as a resend.
    """
    total_sent = await db.scalar(
        select(func.count(TenantEmailVerification.id)).where(
            TenantEmailVerification.tenant_id == tenant_uuid,
            TenantEmailVerification.created_at >= since,
        )
    )
    total_sent = int(total_sent or 0)

    first_sent_at = await db.scalar(
        select(TenantEmailVerification.created_at)
        .where(TenantEmailVerification.tenant_id == tenant_uuid)
        .order_by(TenantEmailVerification.created_at.asc())
        .limit(1)
    )

    if first_sent_at and first_sent_at >= since:
        return max(0, total_sent - 1)
    return total_sent


async def enforce_verification_send_policy(
    tenant_uuid,
    db: AsyncSession,
    *,
    current_time: Optional[datetime] = None,
):
    """
    Apply resend controls for every verification email after the initial send.
    """
    current_time = current_time or now_utc()

    latest_sent_at = await db.scalar(
        select(TenantEmailVerification.created_at)
        .where(TenantEmailVerification.tenant_id == tenant_uuid)
        .order_by(TenantEmailVerification.created_at.desc())
        .limit(1)
    )

    # No prior verification email means this is the initial send, not a resend.
    if not latest_sent_at:
        return

    next_allowed_at = latest_sent_at + timedelta(
        seconds=EMAIL_VERIFICATION_RESEND_MIN_INTERVAL_SECONDS
    )
    if current_time < next_allowed_at:
        retry_after_seconds = max(
            1, int((next_allowed_at - current_time).total_seconds())
        )
        raise HTTPException(
            status_code=429,
            detail=(
                "Please wait before requesting another verification email. "
                f"Try again in {retry_after_seconds} seconds."
            ),
        )

    resends_last_hour = await _count_verification_resends_since(
        tenant_uuid,
        db,
        since=current_time - timedelta(hours=1),
    )
    if resends_last_hour >= EMAIL_VERIFICATION_RESEND_MAX_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail="Verification email resend limit reached for the last hour.",
        )

    resends_last_day = await _count_verification_resends_since(
        tenant_uuid,
        db,
        since=current_time - timedelta(days=1),
    )
    if resends_last_day >= EMAIL_VERIFICATION_RESEND_MAX_PER_DAY:
        raise HTTPException(
            status_code=429,
            detail="Verification email resend limit reached for the last 24 hours.",
        )

# Status transition rules
TENANT_STATUS_TRANSITIONS = {
    TenantStatus.PENDING: [TenantStatus.ACTIVE, TenantStatus.SUSPENDED, TenantStatus.DEACTIVATED],
    TenantStatus.ACTIVE: [TenantStatus.SUSPENDED, TenantStatus.DEACTIVATED],
    TenantStatus.SUSPENDED: [TenantStatus.ACTIVE, TenantStatus.DEACTIVATED],
    TenantStatus.DEACTIVATED: [TenantStatus.ACTIVE],  # No transitions allowed from DEACTIVATED,
}

TENANT_USER_STATUS_TRANSITIONS = {
    TenantUserStatus.ACTIVE: [TenantUserStatus.SUSPENDED],
    TenantUserStatus.SUSPENDED: [TenantUserStatus.ACTIVE],
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
                payload = r.json()
                # auth-service currently returns: {"success": true, "data": {"user_id": ..., "roles": [...]}}
                # but older/alternate versions may return {"role": "..."} / {"roles": [...]}
                role_payload = payload.get("data") if isinstance(payload, dict) else None
                if not isinstance(role_payload, dict):
                    role_payload = payload if isinstance(payload, dict) else {}

                # Prefer single role field if present
                if isinstance(role_payload.get("role"), str):
                    role = role_payload["role"].strip()
                    return [role] if role else []

                roles = role_payload.get("roles") or []
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

    invalidated_at = now_utc()
    await enforce_verification_send_policy(created.id, db, current_time=invalidated_at)
    await invalidate_pending_verification_tokens(created.id, db, invalidated_at=invalidated_at)

    token = generate_email_verification_token()
    expiry = invalidated_at + timedelta(minutes=EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES)

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

    verification_link = f"{EMAIL_VERIFICATION_LINK}/api/v1/multi-tenant/email/verify?token={token}"

    background_tasks.add_task(
        send_verification_email,
        payload.contact_email,
        verification_link,
        tenant_id=created.tenant_id,  # Pass tenant_id for resend reference
        expires_in_minutes=EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES,
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
        TenantRegisterResponse with tenant details. Verification email is sent automatically after creation.
    """

    if payload.contact_email:
        # Use hashed email (normalized + SHA256) for fast, indexed duplicate detection.
        email_hash_value = hash_email(payload.contact_email)

        existing = await db.scalar(
            select(Tenant).where(Tenant.email_hash == email_hash_value)
        )

        if existing:
            # Check status and raise appropriate errors
            if existing.status == TenantStatus.PENDING:
                # Tenant already exists and is pending verification.
                # Do NOT automatically resend verification email here to avoid confusion.
                raise ValueError("Tenant is already registered in pending state. Need email verification")
            elif existing.status == TenantStatus.ACTIVE:
                raise ValueError("Tenant already active")
            elif existing.status == TenantStatus.SUSPENDED:
                raise ValueError("Tenant is suspended. Contact your platform administrator.")
            elif existing.status == TenantStatus.DEACTIVATED:
                raise ValueError("Tenant is deactivated. Contact your platform administrator.")
            
    from utils.utils import _normalize_domain , _domains_similar

    requested_domain_norm = _normalize_domain(payload.domain) if payload.domain else ""
    if requested_domain_norm:
        existing_domain_norm = await db.scalars(select(Tenant).where(Tenant.domain == requested_domain_norm))
        existing_domain_norm = existing_domain_norm.first()

        if existing_domain_norm:
            if existing_domain_norm.domain == requested_domain_norm:
                raise ValueError("Domain already registered")
            if _domains_similar(existing_domain_norm.domain, requested_domain_norm):
                raise ValueError(f"Domain '{payload.domain}' is too similar to existing registered domain '{tenant.domain}'")

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
        # Store hash of normalized email for fast uniqueness checks
        "email_hash": hash_email(payload.contact_email) if payload.contact_email else None,
        "phone_number": encrypted_phone,
        "domain": payload.domain,
        # "subdomain": subdomain,
        "schema_name": schema_name,
        "subscriptions": subscription_strings,
        "quotas": quotas_dict,
        "usage": usage_dict,
        "status": TenantStatus.PENDING,
        "temp_admin_username": "",                 # Will be set upon email verification
        "temp_admin_password_hash": "",            # No password at registration; generated on verification if needed
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

    # Automatically send initial verification email to the tenant contact email.
    # This creates the verification token and schedules the actual email via background tasks.
    await send_initial_verification_email(
        tenant_id=created.tenant_id,
        db=db,
        background_tasks=background_tasks,
    )

    response = TenantRegisterResponse(
        id=created.id,
        tenant_id=created.tenant_id,
        schema_name=created.schema_name,
        subscriptions=created.subscriptions or [],
        quotas=created.quotas or {},
        usage_quota=created.usage or {},
        status=created.status.value if hasattr(created.status, "value") else str(created.status),
        message="Tenant successfully created. A verification email has been sent.",
    )

    return response


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
    
    if tenant.status == TenantStatus.ACTIVE:
        raise ValueError("Tenant already verified and active")
    
    if tenant.status == TenantStatus.SUSPENDED:
        raise ValueError("Tenant is suspended. Contact support.")
    
    if tenant.status == TenantStatus.DEACTIVATED:
        raise ValueError("Tenant is deactivated. Contact support.")

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

    # Ensure this token is still within its validity window
    current_time = now_utc()
    if verification.expires_at <= current_time:
        raise ValueError("Token expired")

    tenant = await tenant_db.get(Tenant, verification.tenant_id)
    if not tenant:
        raise ValueError("Tenant not found for this verification token")

    # Check if tenant is already verified/active
    if tenant.status == TenantStatus.ACTIVE:
        raise ValueError("Tenant email already verified")
    
    if tenant.status == TenantStatus.SUSPENDED:
        raise ValueError("Tenant is suspended. Contact support.")

    await invalidate_pending_verification_tokens(tenant.id, tenant_db, invalidated_at=current_time)
    verification.verified_at = now_utc()
    tenant.status = TenantStatus.ACTIVE

    # Use password from registration request instead of generating one
    # Decrypt the password that was stored during tenant registration
    admin_username = f"admin@{tenant.tenant_id}"
    plain_password = generate_random_password(length = 8)

    hashed_password = hash_password(plain_password)

    tenant.temp_admin_username = admin_username
    tenant.temp_admin_password_hash = hashed_password

    # Create tenant admin user in auth-service via /api/v1/auth/register
    # Store the password provided during registration so tenant admin can login with it
    try:
        async with httpx.AsyncClient(timeout=API_GATEWAY_TIMEOUT) as client:
            # Decrypt email and phone_number before sending to auth service
            try:
                decrypted_email = decrypt_sensitive_data(tenant.contact_email) if tenant.contact_email else None
                decrypted_phone = decrypt_sensitive_data(tenant.phone_number) if tenant.phone_number else None
            except DecryptionError as e:
                logger.error(f"Decryption failed for tenant {tenant.tenant_id}: {e}")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to decrypt tenant contact data. Ensure API_KEY_ENCRYPTION_KEY / JWT_SECRET_KEY matches the key used to encrypt stored data."
                )
            
            if not decrypted_email:
                raise HTTPException(status_code=400, detail="Tenant email not found or invalid")

            auth_response = await client.post(
                f"{API_GATEWAY_URL}/api/v1/auth/register",
                json={
                    "email": decrypted_email,
                    "username": admin_username,
                    "password": plain_password,  # Password from registration request
                    "confirm_password": plain_password,
                    "full_name": tenant.organization_name,
                    "phone_number": decrypted_phone,
                    "timezone": "UTC",
                    "language": "en",
                    "tenant_id": tenant.tenant_id,
                    "is_tenant": True,
                },
            )
    except httpx.RequestError as e:
        logger.error(f"Failed to call auth-service for tenant admin registration: {e}")
        raise HTTPException(
            status_code=503,
            detail="Authentication service unavailable while creating tenant admin user",
        )

    # auth-service /auth/register returns HTTP 200 (not 201) on success.
    # Treat both 200 and 201 as success to avoid surfacing the upstream payload.
    if auth_response.status_code not in (200, 201):
        logger.error(
            f"Auth-service /api/v1/auth/register failed for tenant {tenant.tenant_id}: "
            f"status={auth_response.status_code}, body={auth_response.text}"
        )
        
        raise HTTPException(
            status_code=auth_response.status_code,
            detail=auth_response.json() if auth_response.headers.get("content-type", "").startswith("application/json") else auth_response.text,
        )

    auth_user_payload = auth_response.json()
    # auth-service responses are wrapped like: {"success": true, "data": {...}}
    auth_data = auth_user_payload.get("data") if isinstance(auth_user_payload, dict) else None
    admin_user_id = auth_data.get("id") if isinstance(auth_data, dict) else None
    if not admin_user_id:
        logger.error(
            f"Auth-service did not return user id for tenant admin {tenant.tenant_id}: {auth_user_payload}"
        )
        raise HTTPException(
            status_code=500,
            detail="Authentication service response missing user id for tenant admin",
        )



    # Assign TENANT ADMIN role to the tenant admin user
    # The register endpoint assigns USER role by default, so we need to replace it with TENANT ADMIN
    try:
        # Get TENANT ADMIN role ID from auth_db using ORM
        role_result = await auth_db.execute(
            select(Role.id).where(Role.name == "TENANT ADMIN")
        )
        tenant_admin_role_id = role_result.scalar_one_or_none()

        if tenant_admin_role_id is not None:
            # Delete any existing role assignments (auth-service only allows one role per user)
            await auth_db.execute(
                delete(UserRole).where(UserRole.user_id == admin_user_id)
            )

            # Insert TENANT ADMIN role assignment
            auth_db.add(
                UserRole(
                    user_id=admin_user_id,
                    role_id=tenant_admin_role_id,
                )
            )
            await auth_db.commit()
            logger.info(f"Assigned TENANT ADMIN role to tenant admin user_id={admin_user_id} for tenant {tenant.tenant_id}")
        else:
            logger.warning(f"TENANT ADMIN role not found in auth_db. Tenant admin user_id={admin_user_id} will have default USER role.")
    except Exception as e:
        logger.error(f"Failed to assign TENANT ADMIN role to tenant admin user_id={admin_user_id} for tenant {tenant.tenant_id}: {e}")
        # Don't fail the tenant registration if role assignment fails - user can still be assigned role later
        await auth_db.rollback()

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
    
    logger.info(f"Tenant verified and activated: {tenant.tenant_id}")

    tenant_id_str = str(tenant.tenant_id)
    contact_email_str = decrypted_email
    admin_username_str = str(tenant.temp_admin_username) if tenant.temp_admin_username else admin_username
    password_str = str(plain_password)

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
    
    # Reuse the same send path so expiry, rate limits, and token invalidation stay consistent.
    class _Payload(BaseModel):
        contact_email: EmailStr

    try:
        decrypted_email = decrypt_sensitive_data(tenant.contact_email) if tenant.contact_email else None
    except DecryptionError as e:
        logger.error(f"Decryption failed while preparing resend for tenant {tenant.tenant_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to decrypt tenant contact data for resend. Ensure API_KEY_ENCRYPTION_KEY / JWT_SECRET_KEY matches the key used to encrypt stored data."
        )

    if not decrypted_email:
        raise HTTPException(status_code=400, detail="Tenant email not found or invalid")

    payload = _Payload(contact_email=decrypted_email)
    token = await send_verification_link(
        created=tenant,
        payload=payload,
        db=db,
        subdomain=None,
        background_tasks=background_tasks,
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
        message="Service updated successfully",
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


async def delete_service(
    payload: ServiceDeleteRequest,
    db: AsyncSession,
) -> ServiceDeleteResponse:
    """
    Delete a service configuration by its ID.

    Args:
        payload: Service delete request payload
        db: Database session

    Returns:
        ServiceDeleteResponse: Deletion confirmation
    """

    service = await db.get(ServiceConfig, payload.service_id)

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    try:
        await db.delete(service)
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        logger.error(
            f"Integrity error while deleting service | service_id={payload.service_id}: {e}"
        )
        raise HTTPException(
            status_code=409,
            detail="Service deletion failed due to integrity constraint violation",
        )
    except Exception as e:
        await db.rollback()
        logger.exception(
            f"Error committing service deletion to database | service_id={payload.service_id}: {e}"
        )
        raise HTTPException(status_code=500, detail="Failed to delete service")

    logger.info(f"Service deleted successfully | service_id={payload.service_id}")

    return ServiceDeleteResponse(
        service_id=payload.service_id,
        message="Service deleted successfully",
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
        select(ServiceConfig)
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
    
    # No password collected in create-user flow; generate one so user can set password later (e.g. via reset)
    user_password = generate_random_password(length=12)

    # Create user in AUTH-SERVICE via /api/v1/auth/register
    try:
        async with httpx.AsyncClient(timeout=API_GATEWAY_TIMEOUT) as client:
            auth_response = await client.post(
                f"{API_GATEWAY_URL}/api/v1/auth/register",
                json={
                    "email": payload.email,
                    "username": payload.username,
                    "password": user_password,
                    "confirm_password": user_password,
                    "full_name": payload.full_name,
                    "phone_number": payload.phone_number,
                    "timezone": "UTC",
                    "language": "en",
                    "tenant_id": tenant.tenant_id,
                    "is_tenant": False,
                },
            )
    except httpx.RequestError as e:
        logger.error(f"Failed to call auth-service for tenant user registration: {e}")
        raise HTTPException(
            status_code=503,
            detail="Authentication service unavailable while creating tenant user",
        )

    # auth-service /auth/register returns HTTP 200 (not 201) on success.
    # Treat both 200 and 201 as success.
    if auth_response.status_code not in (200, 201):
        logger.error(
            f"Auth-service /api/v1/auth/register failed for tenant user {payload.username} "
            f"under tenant {tenant.tenant_id}: status={auth_response.status_code}, body={auth_response.text}"
        )
        raise HTTPException(
            status_code=auth_response.status_code,
            detail=auth_response.json() if auth_response.headers.get("content-type", "").startswith("application/json") else auth_response.text,
        )

    auth_user_payload = auth_response.json()
    # auth-service responses are wrapped like: {"success": true, "data": {...}}
    auth_data = auth_user_payload.get("data") if isinstance(auth_user_payload, dict) else None
    user_id = auth_data.get("id") if isinstance(auth_data, dict) else None
    if not user_id:
        logger.error(
            f"Auth-service did not return user id for tenant user {payload.username}: {auth_user_payload}"
        )
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
    
    # Password is stored in auth-service, user can login with the password they provided
    # No need to log or send password via email
    
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


    # Commented out: Sending generated password over email
    # Instead, password is provided by user in request and stored in auth-service
    # User can login with the password they provided via auth/login endpoint
    background_tasks.add_task(
        send_user_welcome_email,
        user_id,
        payload.email,
        None,  # add subdomain if required
        payload.username,
        user_password,
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

    # Removing user status as tenant status and user status is independent of each other 

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

    if tenant_user and tenant_user.status == TenantUserStatus.SUSPENDED:
        raise HTTPException(status_code=400, detail="Cannot update suspended tenant user")
    
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

    if "email" in update_data:
        old_value = decrypt_sensitive_data(tenant_user.email)
        new_value = update_data["email"]
        if old_value != new_value:
            changes["email"] = FieldChange(old=old_value, new=new_value)
            tenant_user.email = encrypt_sensitive_data(new_value) if new_value else None
            updated_fields.append("email")

    # Handle phone_number update (store encrypted)
    if "phone_number" in update_data:
        old_value = decrypt_sensitive_data(tenant_user.phone_number)
        new_value = update_data["phone_number"]
        if old_value != new_value:
            changes["phone_number"] = FieldChange(old=old_value, new=new_value)
            tenant_user.phone_number = encrypt_sensitive_data(new_value) if new_value else None
            updated_fields.append("phone_number")

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
    auth_db: AsyncSession,
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

    # If the user has no other tenant memberships, also delete from auth_db.
    # This prevents deleted tenant users from still being able to login.
    try:
        tenant_memberships = await db.scalar(
            select(func.count()).select_from(TenantUser).where(TenantUser.user_id == payload.user_id)
        )
    except Exception as e:
        logger.exception(
            f"Error counting tenant memberships for deletion | tenant_id={payload.tenant_id} user_id={payload.user_id}: {e}"
        )
        raise HTTPException(status_code=500, detail="Failed to validate tenant user memberships")

    if tenant_memberships == 1:
        # Delete auth user first so login is blocked immediately (tenant DB update happens next).
        try:
            await auth_db.execute(delete(UserDB).where(UserDB.id == payload.user_id))
            await auth_db.commit()
        except IntegrityError as e:
            await auth_db.rollback()
            logger.error(
                f"Integrity error while deleting auth user | user_id={payload.user_id}: {e}"
            )
            raise HTTPException(
                status_code=409,
                detail="Auth user deletion failed due to integrity constraint violation",
            )
        except Exception as e:
            await auth_db.rollback()
            logger.exception(
                f"Error committing auth user deletion | tenant_id={payload.tenant_id} user_id={payload.user_id}: {e}"
            )
            raise HTTPException(status_code=500, detail="Failed to delete auth user")
    else:
        logger.info(
            f"Skipping auth user deletion because user has other tenant memberships | tenant_id={payload.tenant_id} user_id={payload.user_id} memberships={tenant_memberships}"
        )

    # If the deleted user was the tenant admin, clear the foreign reference in tenant DB.
    if tenant.user_id == payload.user_id:
        tenant.user_id = None

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

    if tenant.status == TenantStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Cannot update tenant while status is PENDING",
        )
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
    
    # Handle phone_number update (store encrypted)
    if "phone_number" in update_data:
        old_value = decrypt_sensitive_data(tenant.phone_number)
        new_value = update_data["phone_number"]
        if old_value != new_value:
            changes["phone_number"] = FieldChange(old=old_value, new=new_value)
            tenant.phone_number = encrypt_sensitive_data(new_value) if new_value else None
            updated_fields.append("phone_number")
    
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
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id is required")

    stmt = select(TenantUser).where(TenantUser.tenant_id == tenant_id)
    stmt = stmt.order_by(func.lower(TenantUser.username).asc(), TenantUser.id.asc())

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

