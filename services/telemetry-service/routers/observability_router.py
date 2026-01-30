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

logger = logging.getLogger(__name__)

router = APIRouter()

# Global clients (will be initialized in main.py)
opensearch_client: Optional[OpenSearchQueryClient] = None
jaeger_client: Optional[JaegerQueryClient] = None
rbac_enforcer = None  # Casbin enforcer (will be set in main.py)


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
    Admin users see all logs, normal users see only their organization's logs.
    """
    try:
        # Get organization filter (handles RBAC)
        org_filter = get_organization_filter(request, enforcer, "logs.read")
        
        # Build time range
        time_range = None
        if start_time or end_time:
            time_range = {}
            if start_time:
                time_range["start_time"] = start_time
            if end_time:
                time_range["end_time"] = end_time
        
        # Search logs
        result = await opensearch.search_logs(
            organization_filter=org_filter,
            time_range=time_range,
            service=service,
            level=level,
            search_text=search_text,
            page=page,
            size=size
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
    Returns total logs, error count, warning count, breakdown by level and service.
    """
    try:
        # Get organization filter (handles RBAC)
        org_filter = get_organization_filter(request, enforcer, "logs.read")
        
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
            time_range=time_range
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
    """
    try:
        # Get organization filter (handles RBAC)
        org_filter = get_organization_filter(request, enforcer, "logs.read")
        
        # Build time range
        time_range = None
        if start_time or end_time:
            time_range = {}
            if start_time:
                time_range["start_time"] = start_time
            if end_time:
                time_range["end_time"] = end_time
        
        # Get services
        services = await opensearch.get_services_with_logs(
            organization_filter=org_filter,
            time_range=time_range
        )
        
        return {"services": services}
        
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
        org_filter = get_organization_filter(request, enforcer, "traces.read")
        
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
        org_filter = get_organization_filter(request, enforcer, "traces.read")
        
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
        org_filter = get_organization_filter(request, enforcer, "traces.read")
        
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
        org_filter = get_organization_filter(request, enforcer, "traces.read")
        
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

