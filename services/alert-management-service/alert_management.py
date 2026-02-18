"""
Alert Management API for Dynamic Alert Configuration
Provides CRUD operations for customer-specific alert definitions, receivers, and routing rules
"""
import os
import hashlib
import asyncpg
import httpx
from typing import Optional, List, Dict, Any
from fastapi import HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

# Import audit logger
try:
    from utils.audit_logger import (
        log_alert_definition_create, log_alert_definition_update,
        log_alert_definition_delete, log_alert_definition_toggle,
        log_receiver_create, log_receiver_update, log_receiver_delete,
        log_routing_rule_create, log_routing_rule_update, log_routing_rule_delete,
        log_config_sync
    )
    AUDIT_LOGGING_AVAILABLE = True
except ImportError:
    AUDIT_LOGGING_AVAILABLE = False

# Use ai4icore_logging (same as nmt-service, ocr-service)
from ai4icore_logging import get_logger
logger = get_logger(__name__)

# Valid organizations (until organization info is added to API headers)
VALID_ORGANIZATIONS = ["irctc", "kisanmitra", "bashadaan", "beml"]

# Database connection pool (will be initialized on startup)
db_pool: Optional[asyncpg.Pool] = None
auth_db_pool: Optional[asyncpg.Pool] = None

# Database configuration
DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DB_USER = os.getenv("POSTGRES_USER", "dhruva_user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "dhruva_secure_password_2024")
DB_NAME = "alerting_db"

# Auth database configuration (for querying users by role)
AUTH_DB_NAME = "auth_db"

# Sync service configuration
SYNC_SERVICE_URL = os.getenv("ALERT_CONFIG_SYNC_SERVICE_URL", "http://alert-config-sync-service:8097")
SYNC_ENABLED = os.getenv("ALERT_SYNC_ENABLED", "true").lower() == "true"

async def init_db_pool():
    """Initialize database connection pools for alerting_db and auth_db"""
    global db_pool, auth_db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            min_size=5,
            max_size=50,  # Increased to handle more concurrent requests
            max_inactive_connection_lifetime=300,  # Close idle connections after 5 minutes
            max_queries=50000,  # Maximum queries per connection before recycling
            command_timeout=60  # Timeout for database commands
        )
    
    # Initialize auth_db connection pool for querying users by role
    if auth_db_pool is None:
        auth_db_pool = await asyncpg.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=AUTH_DB_NAME,
            min_size=2,
            max_size=10,
            max_inactive_connection_lifetime=300,
            max_queries=50000,
            command_timeout=60
        )

async def close_db_pool():
    """Close database connection pools"""
    global db_pool, auth_db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None
    if auth_db_pool:
        await auth_db_pool.close()
        auth_db_pool = None

async def ensure_db_pool():
    """Ensure database connection pools are initialized"""
    global db_pool, auth_db_pool
    if db_pool is None or auth_db_pool is None:
        await init_db_pool()
    if db_pool is None:
        raise HTTPException(
            status_code=503,
            detail="Database connection pool not initialized"
        )

async def get_users_by_role(role_name: str) -> List[str]:
    """
    Query users with a specific RBAC role from auth_db and return their email addresses.
    
    Args:
        role_name: RBAC role name (ADMIN, MODERATOR, USER, GUEST)
    
    Returns:
        List of email addresses for users with the specified role
    
    Raises:
        HTTPException: If role is invalid or database error occurs
    """
    # Validate role name
    valid_roles = ["ADMIN", "MODERATOR", "USER", "GUEST"]
    if role_name not in valid_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid RBAC role '{role_name}'. Must be one of: {', '.join(valid_roles)}"
        )
    
    await ensure_db_pool()
    
    if auth_db_pool is None:
        raise HTTPException(
            status_code=503,
            detail="Auth database connection pool not initialized"
        )
    
    try:
        async with auth_db_pool.acquire() as conn:
            # Query users with the specified role
            # Join users -> user_roles -> roles to get users with the role
            rows = await conn.fetch(
                """
                SELECT DISTINCT u.email
                FROM users u
                INNER JOIN user_roles ur ON u.id = ur.user_id
                INNER JOIN roles r ON ur.role_id = r.id
                WHERE r.name = $1
                AND u.is_active = true
                ORDER BY u.email
                """,
                role_name
            )
            
            emails = [row['email'] for row in rows]
            
            if not emails:
                logger.warning(
                    f"No active users found with role '{role_name}'",
                    extra={"context": {"role_name": role_name}}
                )
                raise HTTPException(
                    status_code=404,
                    detail=f"No active users found with role '{role_name}'"
                )
            
            logger.info(
                f"Found {len(emails)} user(s) with role '{role_name}': {', '.join(emails)}",
                extra={"context": {"role_name": role_name, "user_count": len(emails)}}
            )
            return emails
            
    except HTTPException:
        raise
    except asyncpg.exceptions.TooManyConnectionsError:
        logger.error(
            "Auth database connection pool exhausted",
            extra={"context": {"error": "pool_exhausted"}}
        )
        raise HTTPException(
            status_code=503,
            detail="Database connection pool exhausted. Please try again later."
        )
    except Exception as e:
        logger.error(
            f"Error querying users by role '{role_name}': {e}",
            extra={"context": {"role_name": role_name, "error": str(e)}}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to query users by role: {str(e)}"
        )

async def trigger_config_sync(actor: Optional[str] = None, request: Optional[Request] = None) -> None:
    """
    Trigger configuration sync in the sync service.
    This is called after create/update/delete operations to immediately sync changes.
    """
    if not SYNC_ENABLED:
        return
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{SYNC_SERVICE_URL}/sync")
            if response.status_code == 200:
                logger.info(
                    "Configuration sync triggered successfully",
                    extra={"context": {"status": "success", "status_code": 200}}
                )
                # Log audit event for config sync
                if AUDIT_LOGGING_AVAILABLE:
                    log_config_sync(
                        organization=None,  # Sync affects all organizations
                        actor=actor or "system",
                        sync_details={"status": "success", "sync_service_url": SYNC_SERVICE_URL}
                    )
            else:
                logger.warning(
                    f"Sync service returned status {response.status_code}: {response.text}",
                    extra={"context": {"status_code": response.status_code, "response_preview": (response.text[:500] if response.text else None)}}
                )
    except Exception as e:
        # Don't fail the main operation if sync fails
        # Sync will happen on next periodic run anyway
        logger.warning(
            f"Failed to trigger configuration sync: {e}",
            extra={"context": {"error": str(e)}}
        )


def _get_organization_from_api_key(api_key: str) -> str:
    """Map API key to organization name using consistent hashing.
    
    Each API key is randomly mapped to one of the hardcoded customer names.
    Same API key always maps to the same organization.
    """
    # Use hash of API key to consistently map to same organization
    hash_value = int(hashlib.md5(api_key.encode()).hexdigest(), 16)
    org_index = hash_value % len(VALID_ORGANIZATIONS)
    return VALID_ORGANIZATIONS[org_index]

def extract_organization(request: Request) -> str:
    """
    Extract organization/customer ID from request.
    
    Organization is determined by:
    1. X-Organization header (if explicitly provided and valid)
    2. API key hash-based mapping (from X-API-Key or Authorization header)
       - Each API key is randomly mapped to one of the hardcoded customer names
       - Same API key always maps to the same organization
    
    Note: JWT tokens contain user information (username), not organization information.
    Organization details come only from API key hash-based mapping.
    """
    # 1. Check for explicit X-Organization header first
    org_header = request.headers.get("X-Organization") or request.headers.get("x-organization")
    if org_header and org_header.lower() in [o.lower() for o in VALID_ORGANIZATIONS]:
        return org_header.lower()
    
    # 2. Extract API key and use hash-based mapping
    api_key_header = request.headers.get("X-API-Key")
    auth_header = request.headers.get("authorization", "")
    
    api_key: Optional[str] = None
    # Prefer X-API-Key header for organization mapping
    if api_key_header:
        api_key = api_key_header
    elif auth_header:
        # Extract the API key (remove "Bearer " prefix if present)
        # Note: If this is a JWT token, it will still be hashed to get an org
        api_key = auth_header
        if auth_header.startswith("Bearer "):
            api_key = auth_header[7:]
    
    if api_key:
        # Map API key to organization using consistent hashing
        return _get_organization_from_api_key(api_key)
    
    # 3. Fallback: Use hash-based mapping on request identifier for consistency
    # Use a combination of headers/request info to create a consistent identifier
    request_id = (
        request.headers.get("X-Request-ID") or 
        request.headers.get("X-Correlation-ID") or
        str(request.url) + str(request.client.host) if request.client else ""
    )
    if request_id:
        return _get_organization_from_api_key(request_id)
    
    # 4. Final fallback: hash-based mapping using a default identifier
    # This ensures we don't always return the same organization
    return _get_organization_from_api_key("default-request")

def validate_organization(org: str) -> None:
    """Validate that organization is in the allowed list"""
    if org.lower() not in [o.lower() for o in VALID_ORGANIZATIONS]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid organization. Allowed values: {', '.join(VALID_ORGANIZATIONS)}"
        )


def _is_valid_organization(org: Optional[str]) -> bool:
    """Return True if org is in the allowed list (no raise)."""
    if not org:
        return False
    return org.lower() in [o.lower() for o in VALID_ORGANIZATIONS]


def get_organization_for_audit_from_request(
    request: Request,
    admin_provided_org: Optional[str] = None,
) -> Optional[str]:
    """
    Return organization for audit logging only from explicit sources (header or admin input).
    Never use API-key-based mapping. Use this so audit logs record which org's resource
    is affected when that org is known from header or admin; otherwise leave audit org unset.
    """
    if admin_provided_org and _is_valid_organization(admin_provided_org):
        return admin_provided_org.lower()
    org_header = request.headers.get("X-Organization") or request.headers.get("x-organization")
    if org_header and _is_valid_organization(org_header):
        return org_header.lower()
    return None


# Pydantic Models for Request/Response

class AlertAnnotation(BaseModel):
    """Alert annotation model"""
    key: str = Field(..., description="Annotation key (summary, description, impact, action)")
    value: str = Field(..., description="Annotation value")

class AlertDefinitionCreate(BaseModel):
    """Request model for creating an alert definition"""
    name: str = Field(..., description="Alert name (e.g., 'HighLatency')")
    description: Optional[str] = Field(None, description="Alert description")
    promql_expr: str = Field(..., description="PromQL expression (organization will be automatically injected by the API for application alerts only, not for infrastructure alerts)")
    category: str = Field(default="application", description="Category: 'application' or 'infrastructure'")
    severity: str = Field(..., description="Severity: 'critical', 'warning', or 'info'")
    urgency: str = Field(default="medium", description="Urgency: 'high', 'medium', or 'low'")
    alert_type: Optional[str] = Field(None, description="Alert type (e.g., 'latency', 'error_rate')")
    scope: Optional[str] = Field(None, description="Scope (e.g., 'all_services', 'per_service')")
    evaluation_interval: str = Field(default="30s", description="Prometheus evaluation interval")
    for_duration: str = Field(default="5m", description="Duration before alert fires")
    annotations: Optional[List[AlertAnnotation]] = Field(default_factory=list, description="Alert annotations")

class AlertDefinitionUpdate(BaseModel):
    """Request model for updating an alert definition"""
    description: Optional[str] = None
    promql_expr: Optional[str] = None
    category: Optional[str] = None
    severity: Optional[str] = None
    urgency: Optional[str] = None
    alert_type: Optional[str] = None
    scope: Optional[str] = None
    evaluation_interval: Optional[str] = None
    for_duration: Optional[str] = None
    enabled: Optional[bool] = None
    annotations: Optional[List[AlertAnnotation]] = None

class AlertDefinitionResponse(BaseModel):
    """Response model for alert definition"""
    id: int
    organization: str
    name: str
    description: Optional[str]
    promql_expr: str
    category: str
    severity: str
    urgency: str
    alert_type: Optional[str]
    scope: Optional[str]
    evaluation_interval: str
    for_duration: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]
    annotations: List[Dict[str, str]] = Field(default_factory=list)

class NotificationReceiverCreate(BaseModel):
    """Request model for creating a notification receiver (simplified - auto-generates receiver name and routing rule)"""
    category: str = Field(..., description="Category: 'application' or 'infrastructure'")
    severity: str = Field(..., description="Severity: 'critical', 'warning', or 'info'")
    alert_type: Optional[str] = Field(None, description="Optional alert type filter (e.g., 'latency', 'error_rate')")
    email_to: Optional[List[str]] = Field(None, description="Email addresses (required if rbac_role not provided)", min_items=1)
    rbac_role: Optional[str] = Field(None, description="RBAC role name (ADMIN, MODERATOR, USER, GUEST) - if provided, emails will be resolved from users with this role")
    email_subject_template: Optional[str] = Field(None, description="Email subject template")
    email_body_template: Optional[str] = Field(None, description="Email body template (HTML)")
    
    @field_validator('rbac_role')
    @classmethod
    def validate_rbac_role(cls, v):
        """Validate RBAC role if provided"""
        if v is not None:
            valid_roles = ["ADMIN", "MODERATOR", "USER", "GUEST"]
            if v not in valid_roles:
                raise ValueError(f"Invalid RBAC role '{v}'. Must be one of: {', '.join(valid_roles)}")
        return v
    
    def model_post_init(self, __context):
        """Validate that either email_to or rbac_role is provided, but not both"""
        if not self.email_to and not self.rbac_role:
            raise ValueError("Either 'email_to' or 'rbac_role' must be provided")
        if self.email_to and self.rbac_role:
            raise ValueError("Cannot provide both 'email_to' and 'rbac_role'. Use one or the other.")

class NotificationReceiverUpdate(BaseModel):
    """Request model for updating a notification receiver"""
    receiver_name: Optional[str] = None
    email_to: Optional[List[str]] = Field(None, description="Email addresses (required if rbac_role not provided)", min_items=1)
    rbac_role: Optional[str] = Field(None, description="RBAC role name (ADMIN, MODERATOR, USER, GUEST) - if provided, emails will be resolved from users with this role")
    email_subject_template: Optional[str] = None
    email_body_template: Optional[str] = None
    enabled: Optional[bool] = None
    
    @field_validator('rbac_role')
    @classmethod
    def validate_rbac_role(cls, v):
        """Validate RBAC role if provided"""
        if v is not None:
            valid_roles = ["ADMIN", "MODERATOR", "USER", "GUEST"]
            if v not in valid_roles:
                raise ValueError(f"Invalid RBAC role '{v}'. Must be one of: {', '.join(valid_roles)}")
        return v
    
    def model_post_init(self, __context):
        """Validate that if updating email/rbac, either email_to or rbac_role is provided, but not both"""
        # Only validate if at least one is provided (both can be None for other updates)
        if self.email_to is not None or self.rbac_role is not None:
            if self.email_to and self.rbac_role:
                raise ValueError("Cannot provide both 'email_to' and 'rbac_role'. Use one or the other.")

class NotificationReceiverResponse(BaseModel):
    """Response model for notification receiver"""
    id: int
    organization: str
    receiver_name: str
    email_to: List[str]
    rbac_role: Optional[str] = None
    email_subject_template: Optional[str]
    email_body_template: Optional[str]
    enabled: bool
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]

class RoutingRuleCreate(BaseModel):
    """Request model for creating a routing rule"""
    rule_name: str = Field(..., description="Unique rule name")
    receiver_id: int = Field(..., description="ID of the notification receiver")
    match_severity: Optional[str] = Field(None, description="Match severity: 'critical', 'warning', 'info', or null (all)")
    match_category: Optional[str] = Field(None, description="Match category: 'application', 'infrastructure', or null (all)")
    match_alert_type: Optional[str] = Field(None, description="Match alert type or null (all)")
    group_by: Optional[List[str]] = Field(default_factory=lambda: ["alertname", "category", "severity", "organization"], description="Labels to group by")
    group_wait: str = Field(default="10s", description="Wait time before sending first notification")
    group_interval: str = Field(default="10s", description="Wait time before sending next notification")
    repeat_interval: str = Field(default="12h", description="Wait time before repeating notification")
    continue_routing: bool = Field(default=False, description="Continue to next matching rule")
    priority: int = Field(default=100, description="Priority (lower = higher priority)")

class RoutingRuleUpdate(BaseModel):
    """Request model for updating a routing rule"""
    rule_name: Optional[str] = None
    receiver_id: Optional[int] = None
    match_severity: Optional[str] = None
    match_category: Optional[str] = None
    match_alert_type: Optional[str] = None
    group_by: Optional[List[str]] = None
    group_wait: Optional[str] = None
    group_interval: Optional[str] = None
    repeat_interval: Optional[str] = None
    continue_routing: Optional[bool] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None

class RoutingRuleTimingUpdate(BaseModel):
    """Request model for updating routing rule timing parameters"""
    category: str = Field(..., description="Category: 'application' or 'infrastructure'")
    severity: str = Field(..., description="Severity: 'critical', 'warning', or 'info'")
    alert_type: Optional[str] = Field(None, description="Optional alert type filter (e.g., 'latency', 'error_rate')")
    priority: Optional[int] = Field(None, description="Optional priority filter (lower = higher priority)")
    group_wait: Optional[str] = Field(None, description="Wait time before sending first notification")
    group_interval: Optional[str] = Field(None, description="Wait time before sending next notification")
    repeat_interval: Optional[str] = Field(None, description="Wait time before repeating notification")

class RoutingRuleResponse(BaseModel):
    """Response model for routing rule"""
    id: int
    organization: str
    rule_name: str
    receiver_id: int
    match_severity: Optional[str]
    match_category: Optional[str]
    match_alert_type: Optional[str]
    group_by: List[str]
    group_wait: str
    group_interval: str
    repeat_interval: str
    continue_routing: bool
    priority: int
    enabled: bool
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]

# Database Operations

def inject_organization_into_promql(promql_expr: str, organization: str) -> str:
    """
    Automatically inject organization filter into PromQL expression.
    
    Finds all label selectors (e.g., {endpoint=~"/.*inference.*"}) and adds
    organization="<organization>" if not already present.
    
    Examples:
        Input:  'metric{endpoint="/test"}[5m]'
        Output: 'metric{endpoint="/test", organization="irctc"}[5m]'
        
        Input:  'metric{organization="irctc", endpoint="/test"}[5m]'
        Output: 'metric{organization="irctc", endpoint="/test"}[5m]' (no change)
        
        Input:  'sum(rate(metric{endpoint="/test"}[5m])) by (le)'
        Output: 'sum(rate(metric{endpoint="/test", organization="irctc"}[5m])) by (le)'
    """
    import re
    
    # Check if organization is already in the expression (quick check)
    if f'organization="{organization}"' in promql_expr:
        return promql_expr
    
    # Pattern to match label selectors: { ... }
    # This regex finds { followed by content (handling quoted strings) until }
    def replace_selector(match):
        selector = match.group(0)  # Full match including braces
        
        # Check if organization is already in this selector
        if 'organization=' in selector:
            return selector  # Already has organization, don't modify
        
        # Add organization to the selector
        # Remove closing brace, add organization, add closing brace
        selector_content = selector[1:-1].strip()  # Content between braces
        
        if not selector_content:
            # Empty selector
            return f'{{organization="{organization}"}}'
        else:
            # Non-empty selector, add organization before closing brace
            return f'{{{selector_content}, organization="{organization}"}}'
    
    # Find all label selectors { ... } in the PromQL expression
    # This pattern matches { followed by any characters (including quoted strings) until }
    # We need to be careful with nested braces, but PromQL selectors typically don't nest
    result = promql_expr
    # Match { ... } where content can include quoted strings, operators, etc.
    # This is a simplified approach - for complex nested cases, a proper parser would be needed
    pattern = r'\{[^}]*\}'
    
    # Replace all selectors
    result = re.sub(pattern, replace_selector, result)
    
    return result

async def create_alert_definition(
    organization: str,
    data: AlertDefinitionCreate,
    created_by: str,
    request: Optional[Request] = None,
    organization_for_audit: Optional[str] = None,
) -> AlertDefinitionResponse:
    """Create a new alert definition"""
    validate_organization(organization)
    
    # Automatically inject organization into PromQL expression only for application alerts
    # Infrastructure alerts (CPU, memory, disk) don't have organization labels
    if data.category == "application":
        promql_expr_with_org = inject_organization_into_promql(data.promql_expr, organization)
    else:
        promql_expr_with_org = data.promql_expr
    
    async with db_pool.acquire() as conn:
        # Insert alert definition
        row = await conn.fetchrow(
            """
            INSERT INTO alert_definitions (
                organization, name, description, promql_expr, category, severity,
                urgency, alert_type, scope, evaluation_interval, for_duration,
                created_by
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING *
            """,
            organization, data.name, data.description, promql_expr_with_org, data.category,
            data.severity, data.urgency, data.alert_type, data.scope,
            data.evaluation_interval, data.for_duration, created_by
        )
        
        alert_id = row['id']
        
        # Insert annotations if provided
        if data.annotations:
            for ann in data.annotations:
                await conn.execute(
                    """
                    INSERT INTO alert_annotations (alert_definition_id, annotation_key, annotation_value)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (alert_definition_id, annotation_key) 
                    DO UPDATE SET annotation_value = EXCLUDED.annotation_value
                    """,
                    alert_id, ann.key, ann.value
                )
        
        # Fetch with annotations
        result = await get_alert_definition_by_id(alert_id, organization)
        
        # Log audit event (org = resource's org; for create use header/admin only, never API-key-derived)
        if AUDIT_LOGGING_AVAILABLE:
            log_alert_definition_create(
                alert_id=alert_id,
                organization=organization_for_audit,
                actor=created_by,
                request=request,
                alert_data=result.model_dump() if hasattr(result, 'model_dump') else result.dict()
            )
        
        return result

async def get_alert_definition_by_id(alert_id: int, organization: Optional[str] = None) -> AlertDefinitionResponse:
    """
    Get alert definition by ID
    
    Args:
        alert_id: Alert definition ID
        organization: Organization to filter by. If None (admin), returns alert regardless of organization
    """
    await ensure_db_pool()
    
    async with db_pool.acquire() as conn:
        if organization:
            validate_organization(organization)
            row = await conn.fetchrow(
                "SELECT * FROM alert_definitions WHERE id = $1 AND organization = $2",
                alert_id, organization
            )
        else:
            # Admin view: get alert regardless of organization
            row = await conn.fetchrow(
                "SELECT * FROM alert_definitions WHERE id = $1",
                alert_id
            )
        
        if not row:
            raise HTTPException(status_code=404, detail="Alert definition not found")
        
        # Fetch annotations
        ann_rows = await conn.fetch(
            "SELECT annotation_key, annotation_value FROM alert_annotations WHERE alert_definition_id = $1",
            alert_id
        )
        annotations = [{"key": r["annotation_key"], "value": r["annotation_value"]} for r in ann_rows]
        
        return AlertDefinitionResponse(
            id=row['id'],
            organization=row['organization'],
            name=row['name'],
            description=row['description'],
            promql_expr=row['promql_expr'],
            category=row['category'],
            severity=row['severity'],
            urgency=row['urgency'],
            alert_type=row['alert_type'],
            scope=row['scope'],
            evaluation_interval=row['evaluation_interval'],
            for_duration=row['for_duration'],
            enabled=row['enabled'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            created_by=row['created_by'],
            annotations=annotations
        )

async def list_alert_definitions(organization: Optional[str] = None, enabled_only: bool = False) -> List[AlertDefinitionResponse]:
    """
    List alert definitions.
    
    Args:
        organization: If provided, filter by organization. If None, return all alerts (admin only).
        enabled_only: If True, only return enabled alerts.
    """
    await ensure_db_pool()
    
    async with db_pool.acquire() as conn:
        # Build query based on whether organization filter is applied
        if organization:
            validate_organization(organization)
            query = "SELECT * FROM alert_definitions WHERE organization = $1"
            params = [organization]
            param_idx = 2
        else:
            # Admin view: return all alerts
            query = "SELECT * FROM alert_definitions WHERE 1=1"
            params = []
            param_idx = 1
        
        if enabled_only:
            query += f" AND enabled = ${param_idx}"
            params.append(True)
            param_idx += 1
        
        query += " ORDER BY created_at DESC"
        
        rows = await conn.fetch(query, *params)
        
        result = []
        for row in rows:
            # Fetch annotations for each alert
            ann_rows = await conn.fetch(
                "SELECT annotation_key, annotation_value FROM alert_annotations WHERE alert_definition_id = $1",
                row['id']
            )
            annotations = [{"key": r["annotation_key"], "value": r["annotation_value"]} for r in ann_rows]
            
            result.append(AlertDefinitionResponse(
                id=row['id'],
                organization=row['organization'],
                name=row['name'],
                description=row['description'],
                promql_expr=row['promql_expr'],
                category=row['category'],
                severity=row['severity'],
                urgency=row['urgency'],
                alert_type=row['alert_type'],
                scope=row['scope'],
                evaluation_interval=row['evaluation_interval'],
                for_duration=row['for_duration'],
                enabled=row['enabled'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                created_by=row['created_by'],
                annotations=annotations
            ))
        
        return result

async def update_alert_definition(alert_id: int, organization: Optional[str], data: AlertDefinitionUpdate, updated_by: str, request: Optional[Request] = None) -> AlertDefinitionResponse:
    """
    Update an alert definition
    
    Args:
        alert_id: Alert definition ID
        organization: Organization to filter by. If None (admin), updates alert regardless of organization
        data: Update data
        updated_by: Username of the user making the update
    """
    await ensure_db_pool()
    
    async with db_pool.acquire() as conn:
        # Check if exists
        if organization:
            validate_organization(organization)
            existing = await conn.fetchrow(
                "SELECT * FROM alert_definitions WHERE id = $1 AND organization = $2",
                alert_id, organization
            )
        else:
            # Admin view: check if alert exists regardless of organization
            existing = await conn.fetchrow(
                "SELECT * FROM alert_definitions WHERE id = $1",
                alert_id
            )
        
        if not existing:
            raise HTTPException(status_code=404, detail="Alert definition not found")
        
        # Use existing organization for the update query
        actual_organization = existing['organization']
        
        # Build update query dynamically
        updates = []
        params = []
        param_idx = 1
        
        if data.description is not None:
            updates.append(f"description = ${param_idx}")
            params.append(data.description)
            param_idx += 1
        if data.promql_expr is not None:
            # Determine the category to check (use new category if being updated, otherwise existing)
            category_to_check = data.category if data.category is not None else existing['category']
            
            # Automatically inject organization into PromQL expression only for application alerts
            # Infrastructure alerts (CPU, memory, disk) don't have organization labels
            if category_to_check == "application":
                promql_expr_with_org = inject_organization_into_promql(data.promql_expr, actual_organization)
            else:
                promql_expr_with_org = data.promql_expr
            
            updates.append(f"promql_expr = ${param_idx}")
            params.append(promql_expr_with_org)
            param_idx += 1
        if data.category is not None:
            updates.append(f"category = ${param_idx}")
            params.append(data.category)
            param_idx += 1
        if data.severity is not None:
            updates.append(f"severity = ${param_idx}")
            params.append(data.severity)
            param_idx += 1
        if data.urgency is not None:
            updates.append(f"urgency = ${param_idx}")
            params.append(data.urgency)
            param_idx += 1
        if data.alert_type is not None:
            updates.append(f"alert_type = ${param_idx}")
            params.append(data.alert_type)
            param_idx += 1
        if data.scope is not None:
            updates.append(f"scope = ${param_idx}")
            params.append(data.scope)
            param_idx += 1
        if data.evaluation_interval is not None:
            updates.append(f"evaluation_interval = ${param_idx}")
            params.append(data.evaluation_interval)
            param_idx += 1
        if data.for_duration is not None:
            updates.append(f"for_duration = ${param_idx}")
            params.append(data.for_duration)
            param_idx += 1
        if data.enabled is not None:
            updates.append(f"enabled = ${param_idx}")
            params.append(data.enabled)
            param_idx += 1
        
        if updates:
            updates.append(f"updated_by = ${param_idx}")
            params.append(updated_by)
            param_idx += 1
            
            params.extend([alert_id, actual_organization])
            query = f"""
                UPDATE alert_definitions 
                SET {', '.join(updates)}
                WHERE id = ${param_idx} AND organization = ${param_idx + 1}
            """
            await conn.execute(query, *params)
        
        # Update annotations if provided
        if data.annotations is not None:
            # Delete existing annotations
            await conn.execute(
                "DELETE FROM alert_annotations WHERE alert_definition_id = $1",
                alert_id
            )
            # Insert new annotations
            for ann in data.annotations:
                await conn.execute(
                    """
                    INSERT INTO alert_annotations (alert_definition_id, annotation_key, annotation_value)
                    VALUES ($1, $2, $3)
                    """,
                    alert_id, ann.key, ann.value
                )
        
        result = await get_alert_definition_by_id(alert_id, organization)
        
        # Log audit event
        if AUDIT_LOGGING_AVAILABLE:
            # Convert existing and result to dict for audit log
            before_dict = dict(existing) if existing else None
            after_dict = result.model_dump() if hasattr(result, 'model_dump') else result.dict()
            log_alert_definition_update(
                alert_id=alert_id,
                organization=actual_organization,
                actor=updated_by,
                request=request,
                before_values=before_dict,
                after_values=after_dict
            )
        
        # Trigger configuration sync to update YAML files and reload Prometheus/Alertmanager
        await trigger_config_sync(actor=created_by, request=request)
        
        return result

async def delete_alert_definition(alert_id: int, organization: Optional[str] = None, deleted_by: Optional[str] = None, request: Optional[Request] = None) -> None:
    """
    Delete an alert definition
    
    Args:
        alert_id: Alert definition ID
        organization: Organization to filter by. If None (admin), deletes alert regardless of organization
        deleted_by: Username of the user making the deletion
        request: FastAPI Request object for audit logging context
    """
    await ensure_db_pool()
    
    # Get alert data before deletion for audit log
    alert_data = None
    actual_organization = organization
    try:
        if organization:
            validate_organization(organization)
            async with db_pool.acquire() as conn:
                alert_data = await conn.fetchrow(
                    "SELECT * FROM alert_definitions WHERE id = $1 AND organization = $2",
                    alert_id, organization
                )
        else:
            async with db_pool.acquire() as conn:
                alert_data = await conn.fetchrow(
                    "SELECT * FROM alert_definitions WHERE id = $1",
                    alert_id
                )
                if alert_data:
                    actual_organization = alert_data['organization']
    except Exception:
        pass  # If we can't get the data, continue with deletion
    
    try:
        async with db_pool.acquire() as conn:
            if organization:
                validate_organization(organization)
                result = await conn.execute(
                    "DELETE FROM alert_definitions WHERE id = $1 AND organization = $2",
                    alert_id, organization
                )
            else:
                # Admin view: delete alert regardless of organization
                result = await conn.execute(
                    "DELETE FROM alert_definitions WHERE id = $1",
                    alert_id
                )
            
            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="Alert definition not found")
            
            # Log audit event
            if AUDIT_LOGGING_AVAILABLE and alert_data:
                log_alert_definition_delete(
                    alert_id=alert_id,
                    organization=actual_organization,
                    actor=deleted_by or "system",
                    request=request,
                    alert_data=dict(alert_data)
                )
    except asyncpg.exceptions.TooManyConnectionsError:
        logger.error(
            "Database connection pool exhausted",
            extra={"context": {"error": "pool_exhausted"}}
        )
        raise HTTPException(
            status_code=503,
            detail="Database connection pool exhausted. Please try again later."
        )
    except Exception as e:
        logger.error(
            f"Error deleting alert definition: {e}",
            extra={"context": {"error": str(e)}},
            exc_info=True
        )
        raise
    
    # Trigger configuration sync to update YAML files and reload Prometheus/Alertmanager
    await trigger_config_sync(actor=deleted_by or "system", request=request)

async def toggle_alert_definition(alert_id: int, organization: Optional[str], enabled: bool, updated_by: str, request: Optional[Request] = None) -> AlertDefinitionResponse:
    """
    Enable or disable an alert definition
    
    Args:
        alert_id: Alert definition ID
        organization: Organization to filter by. If None (admin), updates alert regardless of organization
        enabled: Whether to enable or disable the alert
        updated_by: Username of the user making the update
    """
    await ensure_db_pool()
    
    async with db_pool.acquire() as conn:
        # First, check if alert exists and get its actual organization
        if organization:
            validate_organization(organization)
            existing = await conn.fetchrow(
                "SELECT * FROM alert_definitions WHERE id = $1 AND organization = $2",
                alert_id, organization
            )
        else:
            # Admin view: check if alert exists regardless of organization
            existing = await conn.fetchrow(
                "SELECT * FROM alert_definitions WHERE id = $1",
                alert_id
            )
        
        if not existing:
            raise HTTPException(status_code=404, detail="Alert definition not found")
        
        # Use existing organization for the update query
        actual_organization = existing['organization']
        
        # Update the enabled status
        result = await conn.execute(
            """
            UPDATE alert_definitions 
            SET enabled = $1, updated_by = $2, updated_at = CURRENT_TIMESTAMP
            WHERE id = $3 AND organization = $4
            """,
            enabled, updated_by, alert_id, actual_organization
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Alert definition not found")
        
        result_obj = await get_alert_definition_by_id(alert_id, organization)
        
        # Log audit event
        if AUDIT_LOGGING_AVAILABLE:
            log_alert_definition_toggle(
                alert_id=alert_id,
                organization=actual_organization,
                enabled=enabled,
                actor=updated_by,
                request=request
            )
        
        # Trigger configuration sync to update YAML files and reload Prometheus/Alertmanager
        await trigger_config_sync(actor=updated_by, request=request)
        
        return result_obj

# Similar functions for notification_receivers and routing_rules would follow the same pattern
# For brevity, I'll create simplified versions - full implementations would mirror the alert_definitions pattern

# Default email templates for notification receivers
DEFAULT_EMAIL_SUBJECT_TEMPLATE = "[{{ if eq .GroupLabels.severity \"critical\" }}CRITICAL{{ else if eq .GroupLabels.severity \"warning\" }}WARNING{{ else }}INFO{{ end }}] {{ .GroupLabels.alertname }} - {{ .GroupLabels.organization }}"
DEFAULT_EMAIL_BODY_TEMPLATE = """<h2 style="color: {{ if eq .GroupLabels.severity \"critical\" }}#d32f2f{{ else if eq .GroupLabels.severity \"warning\" }}#f57c00{{ else }}#1976d2{{ end }};">
  {{ if eq .GroupLabels.severity "critical" }}🚨 CRITICAL{{ else if eq .GroupLabels.severity "warning" }}⚠️ WARNING{{ else }}ℹ️ INFO{{ end }}: {{ .GroupLabels.category | title }} Alert
</h2>
<p><strong>Alert:</strong> {{ .GroupLabels.alertname }}</p>
<p><strong>Organization:</strong> {{ .GroupLabels.organization }}</p>
<p><strong>Severity:</strong> {{ .GroupLabels.severity }}</p>
<p><strong>Category:</strong> {{ .GroupLabels.category }}</p>
"""

async def create_notification_receiver(
    organization: str,
    data: NotificationReceiverCreate,
    created_by: str,
    request: Optional[Request] = None,
    organization_for_audit: Optional[str] = None,
) -> NotificationReceiverResponse:
    """
    Create a new notification receiver and automatically create a routing rule.
    
    Receiver name is auto-generated as: <organization>-<severity>-<category>
    A routing rule is automatically created to match alerts with the specified
    category, severity, and optional alert_type.
    
    Supports both direct email addresses (email_to) and RBAC roles (rbac_role).
    If rbac_role is provided, emails will be resolved from users with that role.
    """
    validate_organization(organization)
    
    # Validate category and severity
    if data.category not in ['application', 'infrastructure']:
        raise HTTPException(status_code=400, detail="category must be 'application' or 'infrastructure'")
    if data.severity not in ['critical', 'warning', 'info']:
        raise HTTPException(status_code=400, detail="severity must be 'critical', 'warning', or 'info'")
    
    # Resolve email addresses from RBAC role if provided
    email_to = data.email_to
    rbac_role = data.rbac_role
    
    if rbac_role:
        # Resolve emails from role
        email_to = await get_users_by_role(rbac_role)
        logger.info(
            f"Resolved RBAC role '{rbac_role}' to {len(email_to)} email address(es)",
            extra={"context": {"rbac_role": rbac_role, "email_count": len(email_to)}}
        )
    elif not email_to:
        # This should not happen due to model validation, but double-check
        raise HTTPException(
            status_code=400,
            detail="Either 'email_to' or 'rbac_role' must be provided"
        )
    
    # Auto-generate receiver name: <severity>-<category>
    # Note: Organization prefix is added by the sync service when generating alertmanager.yml
    receiver_name = f"{data.severity}-{data.category}"
    
    # Use default templates if not provided
    email_subject_template = data.email_subject_template or DEFAULT_EMAIL_SUBJECT_TEMPLATE
    email_body_template = data.email_body_template or DEFAULT_EMAIL_BODY_TEMPLATE
    
    await ensure_db_pool()
    
    async with db_pool.acquire() as conn:
        # Check if receiver with this name already exists
        existing = await conn.fetchrow(
            "SELECT id FROM notification_receivers WHERE organization = $1 AND receiver_name = $2",
            organization, receiver_name
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Receiver with name '{receiver_name}' already exists for organization '{organization}'"
            )
        
        # Create the receiver (store both email_to and rbac_role)
        receiver_row = await conn.fetchrow(
            """
            INSERT INTO notification_receivers (
                organization, receiver_name, email_to, rbac_role,
                email_subject_template, email_body_template, created_by
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            organization, receiver_name, email_to, rbac_role,
            email_subject_template, email_body_template, created_by
        )
        
        receiver_id = receiver_row['id']
        
        # Auto-create routing rule
        # Rule name: <organization>-<severity>-<category>[-<alert_type>]
        rule_name = receiver_name
        if data.alert_type:
            rule_name = f"{rule_name}-{data.alert_type}"
        
        # Check if routing rule already exists
        existing_rule = await conn.fetchrow(
            """
            SELECT id FROM routing_rules 
            WHERE organization = $1 
            AND match_severity = $2 
            AND match_category = $3 
            AND (match_alert_type = $4 OR (match_alert_type IS NULL AND $4 IS NULL))
            """,
            organization, data.severity, data.category, data.alert_type
        )
        
        if existing_rule:
            logger.warning(
                f"Routing rule already exists for organization={organization}, "
                f"severity={data.severity}, category={data.category}, alert_type={data.alert_type}. "
                f"Receiver created but routing rule not created.",
                extra={
                    "context": {
                        "organization": organization,
                        "severity": data.severity,
                        "category": data.category,
                        "alert_type": data.alert_type,
                    }
                }
            )
        else:
            # Create routing rule with default values
            await conn.execute(
                """
                INSERT INTO routing_rules (
                    organization, rule_name, receiver_id, match_severity, match_category,
                    match_alert_type, group_by, group_wait, group_interval, repeat_interval,
                    continue_routing, priority, created_by
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                """,
                organization, rule_name, receiver_id, data.severity, data.category,
                data.alert_type, 
                ["alertname", "category", "severity", "organization"],  # Default group_by
                "10s",  # Default group_wait
                "10s",  # Default group_interval
                "12h",  # Default repeat_interval
                False,  # Default continue_routing
                100,    # Default priority
                created_by
            )
            logger.info(
                f"Auto-created routing rule '{rule_name}' for receiver '{receiver_name}' "
                f"(organization={organization}, severity={data.severity}, category={data.category}, alert_type={data.alert_type})",
                extra={
                    "context": {
                        "organization": organization,
                        "receiver_name": receiver_name,
                        "rule_name": rule_name,
                        "severity": data.severity,
                        "category": data.category,
                        "alert_type": data.alert_type,
                    }
                }
            )
        
        result = NotificationReceiverResponse(**dict(receiver_row))
        
        # Log audit event
        if AUDIT_LOGGING_AVAILABLE:
            log_receiver_create(
                receiver_id=receiver_id,
                organization=organization_for_audit,
                actor=created_by,
                request=request,
                receiver_data=result.model_dump() if hasattr(result, 'model_dump') else result.dict()
            )
        
        # Trigger configuration sync to update YAML files and reload Prometheus/Alertmanager
        await trigger_config_sync(actor=created_by, request=request)
        
        return result

async def list_notification_receivers(organization: Optional[str] = None, enabled_only: bool = False) -> List[NotificationReceiverResponse]:
    """
    List notification receivers
    
    Args:
        organization: If provided, filter by organization. If None, return all receivers (admin only).
        enabled_only: If True, only return enabled receivers.
    """
    await ensure_db_pool()
    
    async with db_pool.acquire() as conn:
        if organization:
            validate_organization(organization)
            query = "SELECT * FROM notification_receivers WHERE organization = $1"
            params = [organization]
            param_idx = 2
        else:
            # Admin view: return all receivers
            query = "SELECT * FROM notification_receivers WHERE 1=1"
            params = []
            param_idx = 1
        
        if enabled_only:
            query += f" AND enabled = ${param_idx}"
            params.append(True)
        
        query += " ORDER BY created_at DESC"
        
        rows = await conn.fetch(query, *params)
        return [NotificationReceiverResponse(**dict(row)) for row in rows]

async def create_routing_rule(
    organization: str,
    data: RoutingRuleCreate,
    created_by: str,
    request: Optional[Request] = None,
    organization_for_audit: Optional[str] = None,
) -> RoutingRuleResponse:
    """Create a new routing rule"""
    validate_organization(organization)
    
    async with db_pool.acquire() as conn:
        # Verify receiver belongs to same organization
        receiver = await conn.fetchrow(
            "SELECT organization FROM notification_receivers WHERE id = $1",
            data.receiver_id
        )
        if not receiver:
            raise HTTPException(status_code=404, detail="Notification receiver not found")
        if receiver['organization'] != organization:
            raise HTTPException(status_code=403, detail="Receiver belongs to different organization")
        
        row = await conn.fetchrow(
            """
            INSERT INTO routing_rules (
                organization, rule_name, receiver_id, match_severity, match_category,
                match_alert_type, group_by, group_wait, group_interval, repeat_interval,
                continue_routing, priority, created_by
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            RETURNING *
            """,
            organization, data.rule_name, data.receiver_id, data.match_severity,
            data.match_category, data.match_alert_type, data.group_by,
            data.group_wait, data.group_interval, data.repeat_interval,
            data.continue_routing, data.priority, created_by
        )
        
        result = RoutingRuleResponse(**dict(row))
        
        # Log audit event (org = resource's org; for create use header/admin only)
        if AUDIT_LOGGING_AVAILABLE:
            log_routing_rule_create(
                rule_id=row['id'],
                organization=organization_for_audit,
                actor=created_by,
                request=request,
                rule_data=result.model_dump() if hasattr(result, 'model_dump') else result.dict()
            )
        
        # Trigger configuration sync to update YAML files and reload Prometheus/Alertmanager
        await trigger_config_sync(actor=created_by, request=request)
        
        return result

async def get_notification_receiver_by_id(receiver_id: int, organization: Optional[str] = None) -> NotificationReceiverResponse:
    """
    Get notification receiver by ID
    
    Args:
        receiver_id: Receiver ID
        organization: Organization to filter by. If None (admin), returns receiver regardless of organization
    """
    await ensure_db_pool()
    
    async with db_pool.acquire() as conn:
        if organization:
            validate_organization(organization)
            row = await conn.fetchrow(
                "SELECT * FROM notification_receivers WHERE id = $1 AND organization = $2",
                receiver_id, organization
            )
        else:
            # Admin view: get receiver regardless of organization
            row = await conn.fetchrow(
                "SELECT * FROM notification_receivers WHERE id = $1",
                receiver_id
            )
        
        if not row:
            raise HTTPException(status_code=404, detail="Notification receiver not found")
        return NotificationReceiverResponse(**dict(row))

async def update_notification_receiver(receiver_id: int, organization: Optional[str], data: NotificationReceiverUpdate, updated_by: str, request: Optional[Request] = None) -> NotificationReceiverResponse:
    """
    Update a notification receiver
    
    Args:
        receiver_id: Receiver ID
        organization: Organization to filter by. If None (admin), updates receiver regardless of organization
        data: Update data
        updated_by: Username of the user making the update
    """
    await ensure_db_pool()
    
    async with db_pool.acquire() as conn:
        # Check if exists
        if organization:
            validate_organization(organization)
            existing = await conn.fetchrow(
                "SELECT * FROM notification_receivers WHERE id = $1 AND organization = $2",
                receiver_id, organization
            )
        else:
            # Admin view: check if receiver exists regardless of organization
            existing = await conn.fetchrow(
                "SELECT * FROM notification_receivers WHERE id = $1",
                receiver_id
            )
        
        if not existing:
            raise HTTPException(status_code=404, detail="Notification receiver not found")
        
        # Use existing organization for the update query
        actual_organization = existing['organization']
        
        # Handle RBAC role resolution if provided
        email_to = data.email_to
        rbac_role = data.rbac_role
        
        if rbac_role:
            # Resolve emails from role
            email_to = await get_users_by_role(rbac_role)
            logger.info(
                f"Resolved RBAC role '{rbac_role}' to {len(email_to)} email address(es) for receiver update",
                extra={"context": {"rbac_role": rbac_role, "email_count": len(email_to), "operation": "update_receiver"}}
            )
        elif data.email_to is None and data.rbac_role is None:
            # Neither email_to nor rbac_role provided - keep existing values
            email_to = None
            rbac_role = None
        
        # Build update query dynamically
        updates = []
        params = []
        param_idx = 1
        
        if data.receiver_name is not None:
            updates.append(f"receiver_name = ${param_idx}")
            params.append(data.receiver_name)
            param_idx += 1
        if email_to is not None:
            updates.append(f"email_to = ${param_idx}")
            params.append(email_to)
            param_idx += 1
        if rbac_role is not None:
            updates.append(f"rbac_role = ${param_idx}")
            params.append(rbac_role)
            param_idx += 1
        elif data.email_to is not None:
            # If email_to is explicitly provided (not from rbac_role), clear rbac_role
            updates.append(f"rbac_role = NULL")
        if data.email_subject_template is not None:
            updates.append(f"email_subject_template = ${param_idx}")
            params.append(data.email_subject_template)
            param_idx += 1
        if data.email_body_template is not None:
            updates.append(f"email_body_template = ${param_idx}")
            params.append(data.email_body_template)
            param_idx += 1
        if data.enabled is not None:
            updates.append(f"enabled = ${param_idx}")
            params.append(data.enabled)
            param_idx += 1
        
        if updates:
            # Update updated_at timestamp
            updates.append(f"updated_at = CURRENT_TIMESTAMP")
            
            params.extend([receiver_id, actual_organization])
            query = f"""
                UPDATE notification_receivers 
                SET {', '.join(updates)}
                WHERE id = ${param_idx} AND organization = ${param_idx + 1}
            """
            await conn.execute(query, *params)
        
        result = await get_notification_receiver_by_id(receiver_id, actual_organization)
        
        # Log audit event
        if AUDIT_LOGGING_AVAILABLE:
            before_dict = dict(existing) if existing else None
            after_dict = result.model_dump() if hasattr(result, 'model_dump') else result.dict()
            log_receiver_update(
                receiver_id=receiver_id,
                organization=actual_organization,
                actor=updated_by,
                request=request,
                before_values=before_dict,
                after_values=after_dict
            )
        
        # Trigger configuration sync to update YAML files and reload Prometheus/Alertmanager
        await trigger_config_sync(actor=created_by, request=request)
        
        return result

async def delete_notification_receiver(receiver_id: int, organization: Optional[str] = None, deleted_by: Optional[str] = None, request: Optional[Request] = None) -> None:
    """
    Delete a notification receiver
    
    Args:
        receiver_id: Receiver ID
        organization: Organization to filter by. If None (admin), deletes receiver regardless of organization
        deleted_by: Username of the user making the deletion
        request: FastAPI Request object for audit logging context
    """
    await ensure_db_pool()
    
    # Get receiver data before deletion for audit log
    receiver_data = None
    actual_organization = organization
    try:
        if organization:
            validate_organization(organization)
            async with db_pool.acquire() as conn:
                receiver_data = await conn.fetchrow(
                    "SELECT * FROM notification_receivers WHERE id = $1 AND organization = $2",
                    receiver_id, organization
                )
        else:
            async with db_pool.acquire() as conn:
                receiver_data = await conn.fetchrow(
                    "SELECT * FROM notification_receivers WHERE id = $1",
                    receiver_id
                )
                if receiver_data:
                    actual_organization = receiver_data['organization']
    except Exception:
        pass  # If we can't get the data, continue with deletion
    
    async with db_pool.acquire() as conn:
        if organization:
            validate_organization(organization)
            result = await conn.execute(
                "DELETE FROM notification_receivers WHERE id = $1 AND organization = $2",
                receiver_id, organization
            )
        else:
            # Admin view: delete receiver regardless of organization
            result = await conn.execute(
                "DELETE FROM notification_receivers WHERE id = $1",
                receiver_id
            )
        
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Notification receiver not found")
        
        # Log audit event
        if AUDIT_LOGGING_AVAILABLE and receiver_data:
            log_receiver_delete(
                receiver_id=receiver_id,
                organization=actual_organization,
                actor=deleted_by or "system",
                request=request,
                receiver_data=dict(receiver_data)
            )
    
    # Trigger configuration sync to update YAML files and reload Prometheus/Alertmanager
    await trigger_config_sync(actor=deleted_by or "system", request=request)

async def get_routing_rule_by_id(rule_id: int, organization: Optional[str] = None) -> RoutingRuleResponse:
    """
    Get routing rule by ID
    
    Args:
        rule_id: Rule ID
        organization: Organization to filter by. If None (admin), returns rule regardless of organization
    """
    await ensure_db_pool()
    
    async with db_pool.acquire() as conn:
        if organization:
            validate_organization(organization)
            row = await conn.fetchrow(
                "SELECT * FROM routing_rules WHERE id = $1 AND organization = $2",
                rule_id, organization
            )
        else:
            # Admin view: get rule regardless of organization
            row = await conn.fetchrow(
                "SELECT * FROM routing_rules WHERE id = $1",
                rule_id
            )
        
        if not row:
            raise HTTPException(status_code=404, detail="Routing rule not found")
        return RoutingRuleResponse(**dict(row))

async def update_routing_rule(rule_id: int, organization: Optional[str], data: RoutingRuleUpdate, updated_by: str, request: Optional[Request] = None) -> RoutingRuleResponse:
    """
    Update a routing rule
    
    Args:
        rule_id: Rule ID
        organization: Organization to filter by. If None (admin), updates rule regardless of organization
        data: Update data
        updated_by: Username of the user making the update
    """
    await ensure_db_pool()
    
    async with db_pool.acquire() as conn:
        # Check if exists
        if organization:
            validate_organization(organization)
            existing = await conn.fetchrow(
                "SELECT * FROM routing_rules WHERE id = $1 AND organization = $2",
                rule_id, organization
            )
        else:
            # Admin view: check if rule exists regardless of organization
            existing = await conn.fetchrow(
                "SELECT * FROM routing_rules WHERE id = $1",
                rule_id
            )
        
        if not existing:
            raise HTTPException(status_code=404, detail="Routing rule not found")
        
        # Use existing organization for the update query
        actual_organization = existing['organization']
        
        # Verify receiver if changed
        if data.receiver_id is not None:
            receiver = await conn.fetchrow(
                "SELECT organization FROM notification_receivers WHERE id = $1",
                data.receiver_id
            )
            if not receiver:
                raise HTTPException(status_code=404, detail="Notification receiver not found")
            if receiver['organization'] != actual_organization:
                raise HTTPException(status_code=403, detail="Receiver belongs to different organization")
        
        # Build update query dynamically
        updates = []
        params = []
        param_idx = 1
        
        if data.rule_name is not None:
            updates.append(f"rule_name = ${param_idx}")
            params.append(data.rule_name)
            param_idx += 1
        if data.receiver_id is not None:
            updates.append(f"receiver_id = ${param_idx}")
            params.append(data.receiver_id)
            param_idx += 1
        if data.match_severity is not None:
            updates.append(f"match_severity = ${param_idx}")
            params.append(data.match_severity)
            param_idx += 1
        if data.match_category is not None:
            updates.append(f"match_category = ${param_idx}")
            params.append(data.match_category)
            param_idx += 1
        if data.match_alert_type is not None:
            updates.append(f"match_alert_type = ${param_idx}")
            params.append(data.match_alert_type)
            param_idx += 1
        if data.group_by is not None:
            updates.append(f"group_by = ${param_idx}")
            params.append(data.group_by)
            param_idx += 1
        if data.group_wait is not None:
            updates.append(f"group_wait = ${param_idx}")
            params.append(data.group_wait)
            param_idx += 1
        if data.group_interval is not None:
            updates.append(f"group_interval = ${param_idx}")
            params.append(data.group_interval)
            param_idx += 1
        if data.repeat_interval is not None:
            updates.append(f"repeat_interval = ${param_idx}")
            params.append(data.repeat_interval)
            param_idx += 1
        if data.continue_routing is not None:
            updates.append(f"continue_routing = ${param_idx}")
            params.append(data.continue_routing)
            param_idx += 1
        if data.priority is not None:
            updates.append(f"priority = ${param_idx}")
            params.append(data.priority)
            param_idx += 1
        if data.enabled is not None:
            updates.append(f"enabled = ${param_idx}")
            params.append(data.enabled)
            param_idx += 1
        
        if updates:
            # Update updated_at timestamp
            updates.append(f"updated_at = CURRENT_TIMESTAMP")
            
            params.extend([rule_id, actual_organization])
            query = f"""
                UPDATE routing_rules 
                SET {', '.join(updates)}
                WHERE id = ${param_idx} AND organization = ${param_idx + 1}
            """
            await conn.execute(query, *params)
        
        result = await get_routing_rule_by_id(rule_id, actual_organization)
        
        # Log audit event
        if AUDIT_LOGGING_AVAILABLE:
            before_dict = dict(existing) if existing else None
            after_dict = result.model_dump() if hasattr(result, 'model_dump') else result.dict()
            log_routing_rule_update(
                rule_id=rule_id,
                organization=actual_organization,
                actor=updated_by,
                request=request,
                before_values=before_dict,
                after_values=after_dict
            )
        
        # Trigger configuration sync to update YAML files and reload Prometheus/Alertmanager
        await trigger_config_sync(actor=created_by, request=request)
        
        return result

async def delete_routing_rule(rule_id: int, organization: Optional[str] = None, deleted_by: Optional[str] = None, request: Optional[Request] = None) -> None:
    """
    Delete a routing rule
    
    Args:
        rule_id: Rule ID
        organization: Organization to filter by. If None (admin), deletes rule regardless of organization
        deleted_by: Username of the user making the deletion
        request: FastAPI Request object for audit logging context
    """
    await ensure_db_pool()
    
    # Get rule data before deletion for audit log
    rule_data = None
    actual_organization = organization
    try:
        if organization:
            validate_organization(organization)
            async with db_pool.acquire() as conn:
                rule_data = await conn.fetchrow(
                    "SELECT * FROM routing_rules WHERE id = $1 AND organization = $2",
                    rule_id, organization
                )
        else:
            async with db_pool.acquire() as conn:
                rule_data = await conn.fetchrow(
                    "SELECT * FROM routing_rules WHERE id = $1",
                    rule_id
                )
                if rule_data:
                    actual_organization = rule_data['organization']
    except Exception:
        pass  # If we can't get the data, continue with deletion
    
    async with db_pool.acquire() as conn:
        if organization:
            validate_organization(organization)
            result = await conn.execute(
                "DELETE FROM routing_rules WHERE id = $1 AND organization = $2",
                rule_id, organization
            )
        else:
            # Admin view: delete rule regardless of organization
            result = await conn.execute(
                "DELETE FROM routing_rules WHERE id = $1",
                rule_id
            )
        
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Routing rule not found")
        
        # Log audit event
        if AUDIT_LOGGING_AVAILABLE and rule_data:
            log_routing_rule_delete(
                rule_id=rule_id,
                organization=actual_organization,
                actor=deleted_by or "system",
                request=request,
                rule_data=dict(rule_data)
            )
    
    # Trigger configuration sync to update YAML files and reload Prometheus/Alertmanager
    await trigger_config_sync(actor=deleted_by or "system", request=request)

async def update_routing_rule_timing(
    organization: Optional[str],
    data: RoutingRuleTimingUpdate,
    updated_by: str,
    request: Optional[Request] = None
) -> Dict[str, Any]:
    """
    Update timing parameters (group_wait, group_interval, repeat_interval) for routing rules
    matching the specified criteria.
    
    Args:
        organization: Organization to filter by. If None (admin), updates rules across all organizations.
        data: Update data with category, severity, optional alert_type, optional priority, and timing parameters.
        updated_by: Username of the user making the update
    
    Returns:
        Dictionary with count of updated rules and details
    """
    await ensure_db_pool()
    
    # Validate category and severity
    if data.category not in ['application', 'infrastructure']:
        raise HTTPException(status_code=400, detail="category must be 'application' or 'infrastructure'")
    if data.severity not in ['critical', 'warning', 'info']:
        raise HTTPException(status_code=400, detail="severity must be 'critical', 'warning', or 'info'")
    
    # Check if at least one timing parameter is provided
    if not any([data.group_wait, data.group_interval, data.repeat_interval]):
        raise HTTPException(
            status_code=400,
            detail="At least one timing parameter (group_wait, group_interval, repeat_interval) must be provided"
        )
    
    # Build WHERE params separately (without update params)
    where_params = []
    where_param_idx = 1
    where_conditions_paramed = []
    
    if organization:
        where_conditions_paramed.append(f"organization = ${where_param_idx}")
        where_params.append(organization)
        where_param_idx += 1
    
    where_conditions_paramed.append(f"match_severity = ${where_param_idx}")
    where_params.append(data.severity)
    where_param_idx += 1
    
    where_conditions_paramed.append(f"match_category = ${where_param_idx}")
    where_params.append(data.category)
    where_param_idx += 1
    
    if data.alert_type is not None:
        where_conditions_paramed.append(f"match_alert_type = ${where_param_idx}")
        where_params.append(data.alert_type)
        where_param_idx += 1
    else:
        where_conditions_paramed.append(f"match_alert_type IS NULL")
    
    if data.priority is not None:
        where_conditions_paramed.append(f"priority = ${where_param_idx}")
        where_params.append(data.priority)
        where_param_idx += 1
    
    # Build UPDATE params
    update_params = []
    update_param_idx = where_param_idx
    updates_paramed = []
    
    if data.group_wait is not None:
        updates_paramed.append(f"group_wait = ${update_param_idx}")
        update_params.append(data.group_wait)
        update_param_idx += 1
    
    if data.group_interval is not None:
        updates_paramed.append(f"group_interval = ${update_param_idx}")
        update_params.append(data.group_interval)
        update_param_idx += 1
    
    if data.repeat_interval is not None:
        updates_paramed.append(f"repeat_interval = ${update_param_idx}")
        update_params.append(data.repeat_interval)
        update_param_idx += 1
    
    updates_paramed.append(f"updated_at = CURRENT_TIMESTAMP")
    
    # Combine all params for the query
    all_params = where_params + update_params
    
    async with db_pool.acquire() as conn:
        # First, get the rules that will be updated (for response)
        # Also fetch current timing values to check if they're NULL
        select_query = f"""
            SELECT id, organization, rule_name, match_severity, match_category, match_alert_type, priority,
                   group_wait, group_interval, repeat_interval
            FROM routing_rules
            WHERE {' AND '.join(where_conditions_paramed)}
        """
        matching_rules = await conn.fetch(select_query, *where_params)
        
        if not matching_rules:
            raise HTTPException(
                status_code=404,
                detail=f"No routing rules found matching the criteria: "
                       f"organization={organization or 'all'}, severity={data.severity}, "
                       f"category={data.category}, alert_type={data.alert_type or 'null'}, "
                       f"priority={data.priority or 'any'}"
            )
        
        # If any field is not provided but is NULL in the database, use default values
        # This ensures we don't leave NULL values when defaults exist
        # Check first rule to see if any fields are NULL (all matching rules should have same state)
        first_rule = matching_rules[0]
        if data.group_wait is None and first_rule['group_wait'] is None:
            updates_paramed.append(f"group_wait = '10s'")
        if data.group_interval is None and first_rule['group_interval'] is None:
            updates_paramed.append(f"group_interval = '10s'")
        if data.repeat_interval is None and first_rule['repeat_interval'] is None:
            updates_paramed.append(f"repeat_interval = '12h'")
        
        # Update the rules - only update fields that were explicitly provided
        # This preserves existing values for fields not in the update
        if not updates_paramed:
            raise HTTPException(
                status_code=400,
                detail="No timing parameters provided to update"
            )
        
        update_query = f"""
            UPDATE routing_rules
            SET {', '.join(updates_paramed)}
            WHERE {' AND '.join(where_conditions_paramed)}
        """
        result = await conn.execute(update_query, *all_params)
        
        # Extract count from result (format: "UPDATE N")
        updated_count = int(result.split()[-1]) if result.startswith("UPDATE") else len(matching_rules)
        
        # Trigger configuration sync
        await trigger_config_sync(actor=updated_by, request=request)
        
        return {
            "updated_count": updated_count,
            "updated_rules": [
                {
                    "id": rule['id'],
                    "organization": rule['organization'],
                    "rule_name": rule['rule_name'],
                    "match_severity": rule['match_severity'],
                    "match_category": rule['match_category'],
                    "match_alert_type": rule['match_alert_type'],
                    "priority": rule['priority']
                }
                for rule in matching_rules
            ],
            "updated_fields": {
                k: v for k, v in {
                    "group_wait": data.group_wait,
                    "group_interval": data.group_interval,
                    "repeat_interval": data.repeat_interval
                }.items() if v is not None
            }
        }

async def list_routing_rules(organization: Optional[str] = None, enabled_only: bool = False) -> List[RoutingRuleResponse]:
    """
    List routing rules
    
    Args:
        organization: If provided, filter by organization. If None, return all rules (admin only).
        enabled_only: If True, only return enabled rules.
    """
    await ensure_db_pool()
    
    async with db_pool.acquire() as conn:
        if organization:
            validate_organization(organization)
            query = "SELECT * FROM routing_rules WHERE organization = $1"
            params = [organization]
            param_idx = 2
        else:
            # Admin view: return all rules
            query = "SELECT * FROM routing_rules WHERE 1=1"
            params = []
            param_idx = 1
        
        if enabled_only:
            query += f" AND enabled = ${param_idx}"
            params.append(True)
        
        query += " ORDER BY priority ASC, created_at DESC"
        
        rows = await conn.fetch(query, *params)
        return [RoutingRuleResponse(**dict(row)) for row in rows]

