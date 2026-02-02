"""
Observability Router for Telemetry Service

Provides RBAC-enabled endpoints for querying logs and traces.
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Query, HTTPException, status, Depends
from pydantic import BaseModel, Field

from ai4icore_telemetry import (
    OpenSearchQueryClient,
    JaegerQueryClient,
    get_organization_filter
)
from sqlalchemy import text

logger = logging.getLogger(__name__)

router = APIRouter()

# Global clients (will be initialized in main.py)
opensearch_client: Optional[OpenSearchQueryClient] = None
jaeger_client: Optional[JaegerQueryClient] = None
rbac_enforcer = None  # Casbin enforcer (will be set in main.py)
multi_tenant_db_session = None  # Multi-tenant database session (will be set in main.py)


def get_opensearch_client() -> OpenSearchQueryClient:
    """Dependency to get OpenSearch client."""
    if opensearch_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenSearch client not initialized"
        )
    return opensearch_client


def get_jaeger_client() -> JaegerQueryClient:
    """Dependency to get Jaeger client."""
    if jaeger_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Jaeger client not initialized"
        )
    return jaeger_client


def get_rbac_enforcer():
    """Dependency to get RBAC enforcer."""
    if rbac_enforcer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RBAC enforcer not initialized"
        )
    return rbac_enforcer


async def query_tenant_id_from_db(user_id: str) -> Optional[str]:
    """
    Query tenant_id from multi_tenant_db for a user.
    This is a fallback when tenant_id is missing from JWT token.
    """
    if multi_tenant_db_session is None:
        logger.warning("multi_tenant_db_session is None, cannot query tenant_id")
        return None
    
    try:
        logger.info(f"Querying tenant_id from database for user_id: {user_id} (type: {type(user_id)})")
        logger.info(f"multi_tenant_db_session type: {type(multi_tenant_db_session)}")
        
        async with multi_tenant_db_session() as session:
            logger.info(f"Session created, executing query for user_id: {int(user_id)}")
            # Query tenant_users table for the user
            result = await session.execute(
                text("""
                    SELECT tu.tenant_id
                    FROM tenant_users tu
                    JOIN tenants t ON tu.tenant_uuid = t.id
                    WHERE tu.user_id = :user_id
                    AND t.status = 'ACTIVE'
                    AND tu.status = 'ACTIVE'
                    LIMIT 1
                """),
                {"user_id": int(user_id)}
            )
            logger.info(f"Query executed, fetching result for user_id: {user_id}")
            row = result.fetchone()
            logger.info(f"Query result for user_id {user_id}: row={row}, type={type(row)}")
            if row:
                tenant_id = row[0]
                logger.info(f"Found tenant_id '{tenant_id}' for user {user_id} from database")
                return tenant_id
            else:
                logger.warning(f"No tenant_id found in database for user {user_id} (row is None or empty)")
                return None
    except Exception as e:
        logger.error(f"Error querying tenant_id from database for user {user_id}: {e}", exc_info=True)
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return None


def map_subscription_to_service_name(subscription: str) -> str:
    """
    Map subscription name (e.g., "asr") to actual service name in logs (e.g., "asr-service").
    
    Args:
        subscription: Subscription name from tenant (e.g., "asr", "ocr", "tts")
        
    Returns:
        Service name as it appears in logs (e.g., "asr-service", "ocr-service")
    """
    # Most services follow the pattern: {name}-service
    # Handle special cases if any
    service_name_mapping = {
        "asr": "asr-service",
        "ocr": "ocr-service",
        "tts": "tts-service",
        "nmt": "nmt-service",
        "ner": "ner-service",
        "llm": "llm-service",
        "transliteration": "transliteration-service",
        "language-detection": "language-detection-service",
        "language_detection": "language-detection-service",
        "speaker-diarization": "speaker-diarization-service",
        "speaker_diarization": "speaker-diarization-service",
        "audio-lang-detection": "audio-lang-detection-service",
        "audio_lang_detection": "audio-lang-detection-service",
        "language-diarization": "language-diarization-service",
        "language_diarization": "language-diarization-service",
        "pipeline": "pipeline-service",
    }
    
    # Check if it's already a service name (contains "-service")
    if "-service" in subscription or "_service" in subscription:
        return subscription
    
    # Map subscription name to service name
    return service_name_mapping.get(subscription.lower(), f"{subscription}-service")


async def get_tenant_subscriptions(tenant_id: str) -> Optional[List[str]]:
    """
    Query tenant subscriptions (registered services) from multi_tenant_db.
    Maps subscription names to actual service names as they appear in logs.
    
    Args:
        tenant_id: The tenant identifier
        
    Returns:
        List of service names (as they appear in logs) that the tenant is subscribed to, 
        or None if tenant not found
    """
    if multi_tenant_db_session is None:
        logger.warning("multi_tenant_db_session is None, cannot query tenant subscriptions")
        return None
    
    try:
        logger.debug(f"Querying subscriptions for tenant_id: {tenant_id}")
        
        async with multi_tenant_db_session() as session:
            # Query tenants table for subscriptions
            result = await session.execute(
                text("""
                    SELECT subscriptions
                    FROM tenants
                    WHERE tenant_id = :tenant_id
                    AND status = 'ACTIVE'
                    LIMIT 1
                """),
                {"tenant_id": tenant_id}
            )
            row = result.fetchone()
            
            if row:
                subscriptions = row[0] if row[0] else []
                # Map subscription names to actual service names
                service_names = [map_subscription_to_service_name(sub) for sub in subscriptions]
                logger.debug(f"Found subscriptions for tenant {tenant_id}: {subscriptions} -> mapped to service names: {service_names}")
                return service_names
            else:
                logger.warning(f"No active tenant found with tenant_id: {tenant_id}")
                return None
    except Exception as e:
        logger.error(f"Error querying tenant subscriptions for tenant_id {tenant_id}: {e}", exc_info=True)
        return None


# ==================== Logs Endpoints ====================

@router.get("/logs/search")
async def search_logs(
    request: Request,
    service: Optional[str] = Query(None, description="Filter by service name"),
    level: Optional[str] = Query(None, description="Filter by log level (INFO, WARN, ERROR, DEBUG)"),
    search_text: Optional[str] = Query(None, description="Search text in log messages"),
    start_time: Optional[str] = Query(None, description="Start time (ISO format or timestamp)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format or timestamp)"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(50, ge=1, le=100, description="Results per page"),
    opensearch: OpenSearchQueryClient = Depends(get_opensearch_client),
    enforcer = Depends(get_rbac_enforcer)
):
    """
    Search logs with filters and pagination.
    
    Requires 'logs.read' permission.
    Admin users see all logs, normal users see only their tenant's logs.
    Non-tenant users are denied access.
    Tenant users can only see logs from services registered to their tenant.
    """
    try:
        # Get tenant_id filter (handles RBAC)
        # Returns None for admin (sees all), tenant_id for users, or raises 403 for non-tenant users
        org_filter = await get_organization_filter(
            request, enforcer, "logs.read",
            tenant_id_fallback=query_tenant_id_from_db
        )
        
        # If user is not admin, filter by tenant subscriptions
        tenant_subscriptions = None
        if org_filter:  # Not admin, has tenant_id
            tenant_subscriptions = await get_tenant_subscriptions(org_filter)
            if tenant_subscriptions is None:
                logger.warning(f"Could not retrieve subscriptions for tenant {org_filter}, denying access")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Tenant not found or inactive"
                )
            
            logger.info(f"Filtering logs for tenant {org_filter} by services: {tenant_subscriptions}")
            
            # If user specified a service, validate it's in tenant subscriptions
            if service:
                if service not in tenant_subscriptions:
                    logger.warning(f"User from tenant {org_filter} requested service {service} which is not in subscribed services {tenant_subscriptions}")
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Service '{service}' is not registered to your tenant"
                    )
        
        # Build time range
        time_range = None
        if start_time or end_time:
            time_range = {}
            if start_time:
                time_range["start_time"] = start_time
            if end_time:
                time_range["end_time"] = end_time
        
        # For non-admin users, we need to filter by subscribed services
        # We'll pass this to opensearch which will add it to the query
        # For now, if service is not specified and user is not admin, we need to filter by subscriptions
        # This will be handled by modifying the opensearch query
        
        # Search logs
        result = await opensearch.search_logs(
            organization_filter=org_filter,
            time_range=time_range,
            service=service,
            level=level,
            search_text=search_text,
            page=page,
            size=size,
            allowed_services=tenant_subscriptions  # Pass subscriptions to filter
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching logs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching logs: {str(e)}"
        )


@router.get("/logs/aggregate")
async def get_log_aggregations(
    request: Request,
    start_time: Optional[str] = Query(None, description="Start time (ISO format or timestamp)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format or timestamp)"),
    opensearch: OpenSearchQueryClient = Depends(get_opensearch_client),
    enforcer = Depends(get_rbac_enforcer)
):
    """
    Get log aggregations and statistics.
    
    Requires 'logs.read' permission.
    Admin users see all logs, normal users see only their tenant's logs.
    Non-tenant users are denied access.
    Tenant users can only see aggregations from services registered to their tenant.
    Returns total logs, error count, warning count, breakdown by level and service.
    """
    try:
        # Get tenant_id filter (handles RBAC)
        # Returns None for admin (sees all), tenant_id for users, or raises 403 for non-tenant users
        org_filter = await get_organization_filter(
            request, enforcer, "logs.read",
            tenant_id_fallback=query_tenant_id_from_db
        )
        
        # If user is not admin, filter by tenant subscriptions
        tenant_subscriptions = None
        if org_filter:  # Not admin, has tenant_id
            tenant_subscriptions = await get_tenant_subscriptions(org_filter)
            if tenant_subscriptions is None:
                logger.warning(f"Could not retrieve subscriptions for tenant {org_filter}, denying access")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Tenant not found or inactive"
                )
        
        # Build time range
        time_range = None
        if start_time or end_time:
            time_range = {}
            if start_time:
                time_range["start_time"] = start_time
            if end_time:
                time_range["end_time"] = end_time
        
        # Get aggregations
        result = await opensearch.get_log_aggregations(
            organization_filter=org_filter,
            time_range=time_range,
            allowed_services=tenant_subscriptions  # Pass subscriptions to filter
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting log aggregations: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting log aggregations: {str(e)}"
        )


@router.get("/logs/services")
async def get_log_services(
    request: Request,
    start_time: Optional[str] = Query(None, description="Start time (ISO format or timestamp)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format or timestamp)"),
    opensearch: OpenSearchQueryClient = Depends(get_opensearch_client),
    enforcer = Depends(get_rbac_enforcer)
):
    """
    Get list of services that have logs.
    
    Requires 'logs.read' permission.
    Admin users see all services, normal users see only services registered to their tenant.
    Non-tenant users are denied access.
    """
    try:
        # Get tenant_id filter (handles RBAC)
        # Returns None for admin (sees all), tenant_id for users, or raises 403 for non-tenant users
        org_filter = await get_organization_filter(
            request, enforcer, "logs.read",
            tenant_id_fallback=query_tenant_id_from_db
        )
        
        # If user is not admin, get tenant subscriptions to filter services
        tenant_subscriptions = None
        if org_filter:  # Not admin, has tenant_id
            tenant_subscriptions = await get_tenant_subscriptions(org_filter)
            if tenant_subscriptions is None:
                logger.warning(f"Could not retrieve subscriptions for tenant {org_filter}, denying access")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Tenant not found or inactive"
                )
        
        # Build time range
        time_range = None
        if start_time or end_time:
            time_range = {}
            if start_time:
                time_range["start_time"] = start_time
            if end_time:
                time_range["end_time"] = end_time
        
        # Get services from OpenSearch
        all_services = await opensearch.get_services_with_logs(
            organization_filter=org_filter,
            time_range=time_range
        )
        
        # Filter services by tenant subscriptions if not admin
        if tenant_subscriptions:
            # Only return services that are both in OpenSearch results AND in tenant subscriptions
            filtered_services = [s for s in all_services if s in tenant_subscriptions]
            logger.info(f"Filtered services for tenant {org_filter}: {filtered_services} (from OpenSearch: {all_services}, from subscriptions: {tenant_subscriptions})")
            return {"services": filtered_services}
        else:
            # Admin sees all services
            logger.debug(f"Admin user - returning all services: {all_services}")
            return {"services": all_services}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting log services: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting log services: {str(e)}"
        )


# ==================== Traces Endpoints ====================

@router.get("/traces/search")
async def search_traces(
    request: Request,
    service: Optional[str] = Query(None, description="Filter by service name"),
    operation: Optional[str] = Query(None, description="Filter by operation name"),
    start_time: Optional[int] = Query(None, description="Start time (microseconds since epoch)"),
    end_time: Optional[int] = Query(None, description="End time (microseconds since epoch)"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of traces"),
    jaeger: JaegerQueryClient = Depends(get_jaeger_client),
    enforcer = Depends(get_rbac_enforcer)
):
    """
    Search traces with filters.
    
    Requires 'traces.read' permission.
    Admin users see all traces, normal users see only their organization's traces.
    """
    try:
        # Get organization filter (handles RBAC)
        org_filter = await get_organization_filter(
            request, enforcer, "traces.read",
            tenant_id_fallback=query_tenant_id_from_db
        )
        
        # Build time range
        time_range = None
        if start_time or end_time:
            time_range = {}
            if start_time:
                time_range["start_time"] = start_time
            if end_time:
                time_range["end_time"] = end_time
        
        # Search traces
        traces = await jaeger.search_traces(
            organization_filter=org_filter,
            service=service,
            operation=operation,
            time_range=time_range,
            limit=limit
        )
        
        return {"data": traces, "total": len(traces), "limit": limit, "offset": 0}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching traces: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching traces: {str(e)}"
        )


@router.get("/traces/{trace_id}")
async def get_trace_by_id(
    trace_id: str,
    request: Request,
    jaeger: JaegerQueryClient = Depends(get_jaeger_client),
    enforcer = Depends(get_rbac_enforcer)
):
    """
    Get a specific trace by ID.
    
    Requires 'traces.read' permission.
    Returns 404 if trace not found or not accessible.
    """
    try:
        # Get organization filter (handles RBAC)
        org_filter = await get_organization_filter(
            request, enforcer, "traces.read",
            tenant_id_fallback=query_tenant_id_from_db
        )
        
        # Get trace
        trace = await jaeger.get_trace_by_id(trace_id, organization_filter=org_filter)
        
        if trace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trace {trace_id} not found or not accessible"
            )
        
        return trace
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trace: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting trace: {str(e)}"
        )


@router.get("/traces/services")
async def get_trace_services(
    request: Request,
    jaeger: JaegerQueryClient = Depends(get_jaeger_client),
    enforcer = Depends(get_rbac_enforcer)
):
    """
    Get list of services that have traces.
    
    Requires 'traces.read' permission.
    """
    try:
        # Get organization filter (handles RBAC)
        org_filter = await get_organization_filter(
            request, enforcer, "traces.read",
            tenant_id_fallback=query_tenant_id_from_db
        )
        
        # Get services
        services = await jaeger.get_services_with_traces(organization_filter=org_filter)
        
        return {"services": services}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trace services: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting trace services: {str(e)}"
        )


@router.get("/traces/services/{service}/operations")
async def get_trace_operations(
    service: str,
    request: Request,
    jaeger: JaegerQueryClient = Depends(get_jaeger_client),
    enforcer = Depends(get_rbac_enforcer)
):
    """
    Get list of operations for a specific service.
    
    Requires 'traces.read' permission.
    """
    try:
        # Get organization filter (handles RBAC)
        org_filter = await get_organization_filter(
            request, enforcer, "traces.read",
            tenant_id_fallback=query_tenant_id_from_db
        )
        
        # Get operations
        operations = await jaeger.get_operations_for_service(service, organization_filter=org_filter)
        
        return {"service": service, "operations": operations}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trace operations: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting trace operations: {str(e)}"
        )

